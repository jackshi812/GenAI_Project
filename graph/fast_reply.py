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
from typing import Callable, Literal

import pyarrow.parquet as pq

from catalog.search import search as catalog_search
from contracts import Citation, RagResult
from graph.relevance import GROCERY_TERMS, catalog_result_is_relevant, normalized_terms


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
    + r"(?:\s*(?:dollars?|bucks?))?",
    re.IGNORECASE,
)
_CURRENCY_PATTERN = re.compile(r"\$\s*(?P<amount>[\d,]+(?:\.\d{1,2})?)")
_BRAND_SOURCE = Path(__file__).resolve().parents[1] / "catalog" / "products.parquet"
_QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "buy",
    "bucks",
    "buck",
    "can",
    "could",
    "do",
    "for",
    "get",
    "i",
    "is",
    "like",
    "me",
    "not",
    "of",
    "please",
    "s",
    "so",
    "some",
    "that",
    "this",
    "the",
    "uh",
    "um",
    "well",
    "what",
    "which",
    "would",
    "you",
}
_BROAD_PRODUCT_TERMS = {
    "cleaner",
    "cleaners",
    "clothes",
    "clothing",
    "food",
    "game",
    "games",
    "groceries",
    "grocery",
    "item",
    "items",
    "product",
    "products",
    "puzzle",
    "puzzles",
    "snack",
    "snacks",
    "toy",
    "toys",
}
_GREETING_PATTERNS = (
    re.compile(r"\bhow are you(?: doing)?\b", re.IGNORECASE),
    re.compile(r"^\s*(?:hi|hello|hey)(?:\b|[!.])", re.IGNORECASE),
    re.compile(r"\bgood (?:morning|afternoon|evening)\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is) up\b", re.IGNORECASE),
)
_THANKS_PATTERN = re.compile(r"\b(?:thanks|thank you)\b", re.IGNORECASE)
_SHOPPING_REQUEST_PATTERN = re.compile(
    r"\b(?:i\s+(?:need|want|would like)|(?:i(?:'m| am)\s+)?looking for|"
    r"find|show|recommend|compare|buy|shop|shopping|product|price|cost|"
    r"budget|under|available|availability|rating|review)\b",
    re.IGNORECASE,
)

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
    turn_kind: Literal[
        "conversation", "catalog", "web_fallback", "no_match"
    ] = "catalog"


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
    query = re.sub(
        r"^\s*(?:hi|hello|hey|good\s+(?:morning|afternoon|evening))\b[\s,.!:-]*",
        "",
        transcript,
        flags=re.IGNORECASE,
    )
    query = _BUDGET_CLAUSE.sub(" ", query)
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
    tokens = query.split()
    query = " ".join(
        token for token in tokens if token.casefold() not in _QUERY_STOPWORDS
    ).strip(" -")
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
    """Return only a catalog brand introduced with an explicit brand cue."""
    normalized = re.sub(r"[^a-z0-9]+", " ", transcript.casefold()).strip()
    padded = f" {normalized} "
    matches: list[tuple[int, int, str]] = []
    for brand in _catalog_brands():
        candidate = re.sub(r"[^a-z0-9]+", " ", brand.casefold()).strip()
        if candidate:
            cues = (
                f" brand {candidate} ",
                f" by {candidate} ",
                f" from {candidate} ",
                f" {candidate} brand ",
            )
            positions = [padded.find(cue) for cue in cues if padded.find(cue) >= 0]
            if positions:
                matches.append((min(positions), -len(candidate), brand))
    return min(matches)[2] if matches else None


def _conversation_reply(transcript: str) -> str | None:
    has_shopping_request = bool(_SHOPPING_REQUEST_PATTERN.search(transcript))
    if (
        not has_shopping_request
        and any(pattern.search(transcript) for pattern in _GREETING_PATTERNS)
    ):
        return "I’m doing well—thanks for asking! What are you shopping for today?"
    if not has_shopping_request and _THANKS_PATTERN.search(transcript):
        return "You’re welcome! Is there another product you’d like me to check?"
    return None


def conversation_reply(transcript: str) -> str | None:
    """Return a fixed social reply when a turn is not a shopping request."""
    return _conversation_reply(transcript)


def _query_terms(value: str) -> set[str]:
    return normalized_terms(value, _QUERY_STOPWORDS)


def _is_specific_product(query: str, explicit_brand: str | None) -> bool:
    terms = _query_terms(query)
    if explicit_brand or any(term.isdigit() for term in terms):
        return True
    return len(terms) >= 2 and not terms.issubset(_BROAD_PRODUCT_TERMS)


def should_search_live(transcript: str) -> bool:
    """Route named/current product requests to one live shopping lookup."""
    query = semantic_query(transcript)
    brand = extract_brand(transcript)
    return bool(_LIVE_TERMS.search(transcript)) or _is_specific_product(query, brand)


def _is_relevant(query: str, result: dict) -> bool:
    return catalog_result_is_relevant(
        query,
        result,
        stopwords=_QUERY_STOPWORDS,
    )


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
    if wants_live:
        catalog_match = f"{title} at {price}" if price else title
        return (
            f"I found {catalog_match} in our 2020 catalog. "
            "I’m checking current listings too."
        )
    if budget_max is not None and product.budget_fit == "within":
        catalog_match = f"{title} at {price}" if price else title
        return (
            f"One option within your ${budget_max:,.0f} budget is "
            f"{catalog_match} from our 2020 catalog."
        )
    if price:
        return f"One catalog option worth a look is {title} at {price}."
    return f"One catalog option worth a look is {title}."


async def build_fast_reply(
    transcript: str,
    *,
    search_fn: Callable[..., list[dict]] = catalog_search,
) -> FastReply:
    """Return one useful catalog-grounded reply without any LLM call."""
    started = time.perf_counter()
    conversation_text = _conversation_reply(transcript)
    if conversation_text:
        return FastReply(
            text=conversation_text,
            product=None,
            citations=(),
            elapsed_ms=int((time.perf_counter() - started) * 1_000),
            live_followup_needed=False,
            turn_kind="conversation",
        )

    budget_max = extract_budget_max(transcript)
    query = semantic_query(transcript)
    brand = extract_brand(transcript)
    category = (
        "Grocery & Gourmet Food"
        if _query_terms(query) & GROCERY_TERMS
        else None
    )
    wants_live = should_search_live(transcript)
    raw_results = await asyncio.to_thread(
        search_fn,
        query=query,
        price_max=budget_max,
        category=category,
        brand=brand,
        k=5,
    )
    relevant = next((item for item in raw_results if _is_relevant(query, item)), None)
    if relevant is None:
        budget_phrase = (
            f" under ${budget_max:,.0f}" if budget_max is not None else ""
        )
        if query == "product":
            text = "I didn’t catch a product request. What would you like me to find?"
            live_followup_needed = False
            turn_kind = "no_match"
        else:
            text = (
                f"I couldn’t find a reliable 2020 catalog match{budget_phrase}, "
                "so I’m checking current web products instead."
            )
            live_followup_needed = True
            turn_kind = "web_fallback"
        return FastReply(
            text=text,
            product=None,
            citations=(),
            elapsed_ms=int((time.perf_counter() - started) * 1_000),
            live_followup_needed=live_followup_needed,
            turn_kind=turn_kind,
        )

    product = RagResult.model_validate(relevant)
    citation = Citation(kind="private", label=product.doc_id, url=None)
    return FastReply(
        text=_compose(product, budget_max, wants_live),
        product=product,
        citations=(citation,),
        elapsed_ms=int((time.perf_counter() - started) * 1_000),
        live_followup_needed=wants_live,
    )


def warm_fast_reply() -> None:
    """Load catalog metadata and embedding runtime before the first voice turn."""
    _catalog_brands()
    catalog_search(query="product", k=1)
