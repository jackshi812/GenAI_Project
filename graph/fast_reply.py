"""Low-latency, catalog-grounded first response for streaming voice sessions.

The full graph remains authoritative for live comparison, matching, conflicts,
and final UI evidence. This module exists only to get a useful first spoken
answer underway before those slower steps finish.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import pyarrow.parquet as pq

from catalog.search import search as catalog_search
from contracts import Citation, RagResult


_LIVE_TERMS = re.compile(
    r"\b(current|currently|today|now|latest|live|available|availability|"
    r"in[ -]?stock|rating|ratings|review|reviews)\b",
    re.IGNORECASE,
)
_BUDGET_PREFIX = re.compile(
    r"\b(?:under|below|less than|up to|at most|maximum|max)\s+(?:\$\s*)?",
    re.IGNORECASE,
)
_NUMBER_WORD = (
    r"zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|"
    r"thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|and"
)
_BUDGET_CLAUSE = re.compile(
    _BUDGET_PREFIX.pattern
    + rf"(?:[\d,]+(?:\.\d{{1,2}})?|(?:(?:{_NUMBER_WORD})[ -]*)+)"
    + r"(?:\s*dollars?)?",
    re.IGNORECASE,
)
_CURRENCY_PATTERN = re.compile(r"\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)")
_BRAND_SOURCE = Path(__file__).resolve().parents[1] / "catalog" / "products.parquet"

_ONES = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_TENS = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}


@dataclass(frozen=True)
class FastReply:
    """The first grounded voice response and its private evidence."""

    text: str
    product: RagResult | None
    citations: tuple[Citation, ...]
    elapsed_ms: int
    live_followup_needed: bool


def _words_to_number(value: str) -> float | None:
    tokens = re.findall(r"[a-z]+", value.casefold().replace("-", " "))
    if not tokens:
        return None
    current = 0
    total = 0
    recognized = False
    for token in tokens:
        if token == "and":
            continue
        if token in _ONES:
            current += _ONES[token]
            recognized = True
        elif token in _TENS:
            current += _TENS[token]
            recognized = True
        elif token == "hundred":
            current = max(current, 1) * 100
            recognized = True
        elif token == "thousand":
            total += max(current, 1) * 1_000
            current = 0
            recognized = True
        else:
            break
    return float(total + current) if recognized else None


def extract_budget_max(transcript: str) -> float | None:
    """Extract a spoken or numeric upper budget without an LLM round trip."""
    prefix = _BUDGET_PREFIX.search(transcript)
    if prefix:
        remainder = transcript[prefix.end() :]
        numeric = re.match(r"[\d,]+(?:\.\d{1,2})?", remainder)
        if numeric:
            return float(numeric.group(0).replace(",", ""))
        spoken = _words_to_number(remainder)
        if spoken is not None:
            return spoken
    currency = _CURRENCY_PATTERN.search(transcript)
    return float(currency.group("amount").replace(",", "")) if currency else None


def semantic_query(transcript: str) -> str:
    """Remove routing/budget language while retaining the requested product."""
    query = _BUDGET_CLAUSE.sub(" ", transcript)
    query = _CURRENCY_PATTERN.sub(" ", query)
    query = _LIVE_TERMS.sub(" ", query)
    query = re.sub(
        r"\b(?:please|can you|could you|would you|i need|i want|find me|find|"
        r"show me|compare|check|the price of|price of|price|catalog|with|the|"
        r"a|an|some|for me)\b",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(r"[^a-zA-Z0-9' -]+", " ", query)
    query = " ".join(query.split()).strip(" -")
    return query or "product"


@lru_cache(maxsize=1)
def _catalog_brands() -> tuple[str, ...]:
    """Load known brands once so a fast reply can apply a safe exact filter."""
    table = pq.read_table(_BRAND_SOURCE, columns=["brand"])
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    for value in table.column("brand").to_pylist():
        brand = str(value or "").strip()
        if brand:
            spellings[brand.casefold()][brand] += 1
    brands = {
        counts.most_common(1)[0][0]
        for counts in spellings.values()
    }
    return tuple(sorted(brands, key=len, reverse=True))


def extract_brand(transcript: str) -> str | None:
    """Return a catalog-known brand explicitly present in the transcript."""
    normalized = re.sub(r"[^a-z0-9]+", " ", transcript.casefold()).strip()
    padded = f" {normalized} "
    matches: list[tuple[int, int, str]] = []
    for brand in _catalog_brands():
        candidate = re.sub(r"[^a-z0-9]+", " ", brand.casefold()).strip()
        if candidate:
            position = padded.find(f" {candidate} ")
            if position >= 0:
                matches.append((position, -len(candidate), brand))
    return min(matches)[2] if matches else None


def _money(value: float | str | None) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"${float(value):,.2f}"
    raw = str(value or "").strip()
    return raw or None


def _spoken_title(title: str, limit: int = 6) -> str:
    words = title.split()
    for index, word in enumerate(words):
        marker = word.casefold().strip(",.;:-()")
        if index >= 3 and marker in {"with", "includes", "including"}:
            words = words[:index]
            break
    words = words[:limit]
    while words and words[-1].casefold().strip(",.;:-()") in {
        "with",
        "and",
        "for",
        "of",
        "the",
        "a",
        "an",
        "by",
        "in",
    }:
        words.pop()
    return " ".join(words).rstrip(",.;:-")


def _compose(product: RagResult, budget_max: float | None, wants_live: bool) -> str:
    title = _spoken_title(product.title)
    price = _money(product.price_low if product.price_low is not None else product.price)
    if price:
        first = f"Sure—I found {title} at {price} in our 2020 catalog."
    else:
        first = f"Sure—I found {title} in our 2020 catalog."

    # Keep the first utterance deliberately short. Live/web work continues in
    # the background and gets its own provenance-aware follow-up.
    if wants_live:
        return first
    if budget_max is not None and product.budget_fit == "within":
        return f"{first} It fits your ${budget_max:,.0f} budget."
    return f"{first} I’ll bring up the details for you."


async def build_fast_reply(
    transcript: str,
    *,
    search_fn: Callable[..., list[dict]] = catalog_search,
) -> FastReply:
    """Return one useful catalog-grounded reply without any LLM call."""
    started = time.perf_counter()
    budget_max = extract_budget_max(transcript)
    wants_live = bool(_LIVE_TERMS.search(transcript))
    query = semantic_query(transcript)
    # Match brands only after routing/budget words are removed. Some derived
    # catalog brands are ordinary words (for example, "Under") and must not
    # be inferred from phrases such as "under $20".
    brand = extract_brand(query)
    raw_results = await asyncio.to_thread(
        search_fn,
        query=query,
        price_max=budget_max,
        brand=brand,
        k=1,
    )
    if not raw_results:
        text = "I couldn’t find a close catalog match yet. Let me try a broader search."
        return FastReply(
            text=text,
            product=None,
            citations=(),
            elapsed_ms=int((time.perf_counter() - started) * 1_000),
            live_followup_needed=wants_live,
        )

    product = RagResult.model_validate(raw_results[0])
    citation = Citation(kind="private", label=product.doc_id, url=None)
    return FastReply(
        text=_compose(product, budget_max, wants_live),
        product=product,
        citations=(citation,),
        elapsed_ms=int((time.perf_counter() - started) * 1_000),
        live_followup_needed=wants_live,
    )
