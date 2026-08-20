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
from contracts import Citation, ComparisonProduct, RagResult, ShoppingContext
from graph.decision import choose_direction, choose_product_index
from graph.dialogue import natural_dialogue_reply
from graph.preferences import (
    clears_budget,
    has_actionable_preference,
    matched_preferences,
    preference_requirements,
    rank_products_by_preferences,
    resolve_preferences,
    strip_new_product_transition,
    with_product_query,
)
from graph.relevance import (
    catalog_result_is_relevant,
    infer_catalog_category,
    normalized_terms,
)
from graph.retriever import RAG_CANDIDATE_K, best_available_facet_pool
from graph.response_style import (
    catalog_recommendation,
    is_delegated_choice,
    is_rejection_followup,
    is_vague_shopping_query,
    refinement_reply,
    web_recommendation,
)
from graph.safety import SAFETY_RATIONALE, is_hazardous_chemical_mixing


_LIVE_TERMS = re.compile(
    r"\b(current|currently|today|now|latest|live|available|availability|"
    r"in[ -]?stock|online|web|internet|rating|ratings|review|reviews)\b",
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
_NUMERIC_AMOUNT = r"[\d,]+(?:\.\d{1,2})?"
_NUMERIC_RANGE_PATTERNS = (
    re.compile(
        rf"\bbetween\s+\$?\s*(?P<low>{_NUMERIC_AMOUNT})"
        rf"(?:\s+(?:and|to)?\s*|\s*-\s*)\$?\s*"
        rf"(?P<high>{_NUMERIC_AMOUNT})(?:\s*(?:dollars?|bucks?))?\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bfrom\s+\$?\s*(?P<low>{_NUMERIC_AMOUNT})\s+to\s+"
        rf"\$?\s*(?P<high>{_NUMERIC_AMOUNT})(?:\s*(?:dollars?|bucks?))?\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\$\s*(?P<low>{_NUMERIC_AMOUNT})\s*(?:-|to)\s*"
        rf"\$?\s*(?P<high>{_NUMERIC_AMOUNT})(?:\s*(?:dollars?|bucks?))?\b",
        re.IGNORECASE,
    ),
)
_SPOKEN_AMOUNT = rf"(?:(?:{_NUMBER_WORD})(?:[ -]+(?:{_NUMBER_WORD}))*)"
_SPOKEN_RANGE_PATTERNS = (
    re.compile(
        rf"\bbetween\s+(?P<low>{_SPOKEN_AMOUNT}?)\s+(?:and|to)\s+"
        rf"(?P<high>{_SPOKEN_AMOUNT})(?:\s+(?:dollars?|bucks?))?\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bfrom\s+(?P<low>{_SPOKEN_AMOUNT}?)\s+to\s+"
        rf"(?P<high>{_SPOKEN_AMOUNT})(?:\s+(?:dollars?|bucks?))?\b",
        re.IGNORECASE,
    ),
)
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
    "from",
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
    "anything",
    "cleaner",
    "cleaners",
    "clothes",
    "clothing",
    "food",
    "game",
    "games",
    "groceries",
    "grocery",
    "home",
    "house",
    "item",
    "items",
    "kitchen",
    "product",
    "products",
    "puzzle",
    "puzzles",
    "snack",
    "snacks",
    "something",
    "toy",
    "toys",
}
_GREETING_PATTERNS = (
    re.compile(r"\bhow are you(?: doing)?\b", re.IGNORECASE),
    re.compile(r"\bhow(?:'s| is) it going(?: with you)?\b", re.IGNORECASE),
    re.compile(r"^\s*(?:hi|hello|hey)(?:\b|[!.])", re.IGNORECASE),
    re.compile(r"\bgood (?:morning|afternoon|evening)\b", re.IGNORECASE),
    re.compile(r"\bwhat(?:'s| is) up\b", re.IGNORECASE),
)
_THANKS_PATTERN = re.compile(r"\b(?:thanks|thank you)\b", re.IGNORECASE)
_CART_COMPLETION_PATTERN = re.compile(
    r"^\s*(?:(?:okay|ok|great|done)[\s,;:!.-]+)?"
    r"(?:(?:i|we)(?:['’]ve|\s+have)?\s+)?"
    r"(?:added|put)\s*"
    r"(?:(?:it|that|this|them|those|these)\s*)?"
    r"(?:(?:to|in)\s*)?"
    r"(?:(?:my|our|the)\s*)?cart\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_BACK_PATTERN = re.compile(
    r"^\s*(?:(?:oh|okay|ok)[\s,;:!.-]+)?(?:no[\s,;:!.-]+)?"
    r"(?:go\s+)?back\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_SEARCH_RESULT_PATTERN = re.compile(
    r"^\s*(?:the\s+)?search\s+results?\s*[.!?]*\s*$",
    re.IGNORECASE,
)
_TERMINATION_PATTERN = re.compile(
    r"^\s*(?:(?:okay|ok|great|thanks|thank\s+you)[\s,;:!.-]+)?"
    r"(?:that(?:['’]s|\s+is)\s+all|(?:i(?:['’]m|\s+am)|we(?:['’]re|\s+are))\s+done|"
    r"all\s+done)\s*[.!?]*\s*$",
    re.IGNORECASE,
)
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
        "conversation",
        "safety",
        "clarification",
        "refinement",
        "selection",
        "preference_update",
        "catalog",
        "web_fallback",
        "no_match",
    ] = "catalog"
    resolved_transcript: str | None = None
    decision_source: str | None = None
    shopping_context: ShoppingContext | None = None


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


def _single_budget_max(transcript: str) -> float | None:
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


def _ordered_bounds(low: float, high: float) -> tuple[float, float]:
    """Normalize a shopper-stated range without guessing a missing endpoint."""
    return (low, high) if low <= high else (high, low)


def extract_budget_bounds(transcript: str) -> tuple[float | None, float | None]:
    """Extract numeric metadata bounds, including common spoken range forms."""
    text = str(transcript or "")
    for pattern in _NUMERIC_RANGE_PATTERNS:
        match = pattern.search(text)
        if match:
            return _ordered_bounds(
                float(match.group("low").replace(",", "")),
                float(match.group("high").replace(",", "")),
            )
    for pattern in _SPOKEN_RANGE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        low = _words_to_number(match.group("low"))
        high = _words_to_number(match.group("high"))
        if low is not None and high is not None:
            return _ordered_bounds(low, high)
    return None, _single_budget_max(text)


def extract_budget_max(transcript: str) -> float | None:
    """Extract a spoken/numeric upper budget without an LLM round trip."""
    return extract_budget_bounds(transcript)[1]


def contextualize_followup(
    transcript: str,
    pending_budget_max: float | None,
    pending_budget_min: float | None = None,
) -> str:
    """Carry a pending budget into one short clarification response."""
    if (
        pending_budget_max is None
        or extract_budget_max(transcript) is not None
        or clears_budget(transcript)
        or _conversation_reply(transcript) is not None
    ):
        return transcript
    if pending_budget_min is not None:
        return (
            f"{transcript.rstrip()} between ${pending_budget_min:g} "
            f"and ${pending_budget_max:g}"
        )
    return f"{transcript.rstrip()} under ${pending_budget_max:g}"


def semantic_query(transcript: str) -> str:
    """Remove routing/budget language while retaining the requested product."""
    query = re.sub(
        r"^\s*(?:(?:hi|hello|hey|good\s+(?:morning|afternoon|evening))\b|"
        r"how\s+are\s+you(?:\s+doing)?\b|"
        r"how(?:'s|\s+is)\s+it\s+going(?:\s+with\s+you)?\b)[\s,.!?:;-]*",
        "",
        transcript,
        flags=re.IGNORECASE,
    )
    query = strip_new_product_transition(query)
    for pattern in (*_NUMERIC_RANGE_PATTERNS, *_SPOKEN_RANGE_PATTERNS):
        query = pattern.sub(" ", query)
    query = _BUDGET_CLAUSE.sub(" ", query)
    query = _CURRENCY_PATTERN.sub(" ", query)
    query = _LIVE_TERMS.sub(" ", query)
    query = re.sub(
        r"\b(?:please|can you|could you|would you|i need|i want|"
        r"i (?:asked|am asking|was asking) for|find me|find|"
        r"show me|give me|give|compare|check|the price of|price of|price|catalog|with|the|"
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
    text = str(transcript or "")
    if _BACK_PATTERN.fullmatch(text):
        return "Sure—let’s go back. What would you like to change?"
    if _SEARCH_RESULT_PATTERN.fullmatch(text):
        return "Those are the search results. What would you like to adjust?"
    if _TERMINATION_PATTERN.fullmatch(text):
        return "All set. Come back anytime you’d like help shopping."
    if _CART_COMPLETION_PATTERN.fullmatch(text):
        return "Great—what would you like to shop for next?"
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


def explicitly_requests_live(transcript: str) -> bool:
    """Whether the shopper directly asks for current/live marketplace facts."""
    return bool(_LIVE_TERMS.search(str(transcript or "")))


def _is_relevant(query: str, result: dict) -> bool:
    return catalog_result_is_relevant(
        query,
        result,
        stopwords=_QUERY_STOPWORDS,
    )


async def build_fast_reply(
    transcript: str,
    *,
    search_fn: Callable[..., list[dict]] = catalog_search,
    dialogue_context: dict | None = None,
    allow_dialogue_llm: bool = True,
) -> FastReply:
    """Return one fast grounded reply, using the LLM only for delegated choices."""
    started = time.perf_counter()
    context = dialogue_context or {}
    prior_shopping_context = context.get("shopping_context")
    if is_hazardous_chemical_mixing(transcript):
        shopping_context = (
            ShoppingContext.model_validate(prior_shopping_context)
            if prior_shopping_context is not None
            else ShoppingContext()
        )
        return FastReply(
            text=SAFETY_RATIONALE,
            product=None,
            citations=(),
            elapsed_ms=int((time.perf_counter() - started) * 1_000),
            live_followup_needed=False,
            turn_kind="safety",
            shopping_context=shopping_context,
        )
    budget_min, budget_max = extract_budget_bounds(transcript)
    explicit_delegated = is_delegated_choice(transcript)
    explicit_actionable_preference = has_actionable_preference(transcript)
    rejection = is_rejection_followup(transcript)
    bare_rejection = bool(
        rejection and not explicit_actionable_preference and not explicit_delegated
    )
    base_query = semantic_query(transcript)
    if bare_rejection:
        shopping_context = (
            ShoppingContext.model_validate(prior_shopping_context)
            if prior_shopping_context is not None
            else ShoppingContext()
        ).model_copy(
            update={
                "is_followup": prior_shopping_context is not None,
                "preference_changed": False,
            },
            deep=True,
        )
    else:
        shopping_context = await resolve_preferences(
            transcript,
            base_query,
            prior_shopping_context,
            allow_llm=False,
        )
    delegated = explicit_delegated or bool(
        is_vague_shopping_query(shopping_context.product_query)
        and (
            preference_requirements(shopping_context)
            or shopping_context.excluded
        )
    )
    actionable_preference = (
        not delegated
        and (
            explicit_actionable_preference
            or shopping_context.preference_changed
        )
    )
    if clears_budget(transcript):
        budget_min = None
        budget_max = None
    elif budget_max is None and (delegated or shopping_context.is_followup):
        budget_min = context.get("budget_min")
        budget_max = context.get("budget_max")

    query: str | None = None
    category: str | None = None
    resolved_transcript: str | None = None
    decision_source: str | None = None
    if delegated:
        prior_products = [
            ComparisonProduct.model_validate(item)
            for item in (context.get("products") or [])
        ]
        if prior_products and not context.get("rejected_previous", False):
            selected_index, decision_source = await choose_product_index(
                transcript,
                prior_products,
            )
            selected = prior_products[selected_index]
            citations: list[Citation] = []
            if selected.private is not None:
                citations.append(
                    Citation(
                        kind="private",
                        label=selected.private.doc_id,
                        url=None,
                    )
                )
            if selected.live is not None:
                citations.append(
                    Citation(
                        kind="live",
                        label=_domain(selected.live.url),
                        url=selected.live.url,
                    )
                )
            previous_request = str(context.get("previous_request") or transcript)
            if selected.private is not None:
                live_price = (
                    float(selected.live.price)
                    if selected.live is not None
                    and isinstance(selected.live.price, (int, float))
                    and not isinstance(selected.live.price, bool)
                    else None
                )
                text = catalog_recommendation(
                    selected.private,
                    query=previous_request,
                    budget_max=budget_max,
                    checking_live=False,
                    current_price=live_price,
                    decisive=True,
                )
            elif selected.live is not None:
                live_price = (
                    float(selected.live.price)
                    if isinstance(selected.live.price, (int, float))
                    and not isinstance(selected.live.price, bool)
                    else None
                )
                text = web_recommendation(
                    selected.live,
                    query=previous_request,
                    budget_max=budget_max,
                    numeric_price=live_price,
                    decisive=True,
                )
            else:
                text = "I don’t have a grounded option to choose from yet."
            return FastReply(
                text=text,
                product=selected.private,
                citations=tuple(citations),
                elapsed_ms=int((time.perf_counter() - started) * 1_000),
                live_followup_needed=False,
                turn_kind="selection",
                decision_source=decision_source,
                shopping_context=shopping_context,
            )

        active_context = (
            ShoppingContext.model_validate(prior_shopping_context)
            if prior_shopping_context is not None
            else None
        )
        can_continue_active_search = bool(
            active_context is not None
            and not prior_products
            and not context.get("rejected_previous", False)
            and not is_vague_shopping_query(active_context.product_query)
        )
        if can_continue_active_search:
            shopping_context = active_context.model_copy(
                update={"is_followup": True},
                deep=True,
            )
            category = infer_catalog_category(shopping_context.product_query)
            decision_source = "active request"
        else:
            direction = await choose_direction(transcript, context)
            category = direction.category
            decision_source = direction.selected_by
            shopping_context = with_product_query(
                shopping_context,
                direction.query,
                understanding_source=(
                    "llm" if direction.selected_by == "llm" else "fallback"
                ),
            )
        query = shopping_context.resolved_query
        resolved_transcript = f"Find {query}"
        if budget_min is not None and budget_max is not None:
            resolved_transcript += f" between ${budget_min:g} and ${budget_max:g}"
        elif budget_max is not None:
            resolved_transcript += f" under ${budget_max:g}"

    if (
        not delegated
        and rejection
        and not actionable_preference
    ):
        return FastReply(
            text=refinement_reply(budget_max),
            product=None,
            citations=(),
            elapsed_ms=int((time.perf_counter() - started) * 1_000),
            live_followup_needed=False,
            turn_kind="refinement",
            shopping_context=shopping_context,
        )

    conversation_text = _conversation_reply(transcript)
    if conversation_text:
        if prior_shopping_context is not None:
            shopping_context = ShoppingContext.model_validate(
                prior_shopping_context
            )
        return FastReply(
            text=conversation_text,
            product=None,
            citations=(),
            elapsed_ms=int((time.perf_counter() - started) * 1_000),
            live_followup_needed=False,
            turn_kind="conversation",
            shopping_context=shopping_context,
        )

    if (
        prior_shopping_context is not None
        and shopping_context.is_followup
        and not shopping_context.preference_changed
        and not actionable_preference
    ):
        return FastReply(
            text=await natural_dialogue_reply(
                "preference",
                transcript,
                budget_max,
                previous_request=str(context.get("previous_request") or ""),
                previous_answer=str(context.get("previous_answer") or ""),
                allow_llm=allow_dialogue_llm,
            ),
            product=None,
            citations=(),
            elapsed_ms=int((time.perf_counter() - started) * 1_000),
            live_followup_needed=False,
            turn_kind="clarification",
            shopping_context=shopping_context,
        )

    query = query or shopping_context.resolved_query or base_query
    if is_vague_shopping_query(shopping_context.product_query or query):
        return FastReply(
            text=await natural_dialogue_reply(
                "clarification",
                transcript,
                budget_max,
                previous_request=str(context.get("previous_request") or ""),
                previous_answer=str(context.get("previous_answer") or ""),
                allow_llm=allow_dialogue_llm,
            ),
            product=None,
            citations=(),
            elapsed_ms=int((time.perf_counter() - started) * 1_000),
            live_followup_needed=False,
            turn_kind="clarification",
            shopping_context=shopping_context,
        )

    if shopping_context.is_followup and resolved_transcript is None:
        resolved_transcript = f"Find {query}"
        if budget_min is not None and budget_max is not None:
            resolved_transcript += f" between ${budget_min:g} and ${budget_max:g}"
        elif budget_max is not None:
            resolved_transcript += f" under ${budget_max:g}"

    brand = None if delegated else extract_brand(transcript)
    if category is None:
        category = infer_catalog_category(query)
    wants_live = (
        False
        if delegated
        else explicitly_requests_live(transcript)
        if preference_requirements(shopping_context)
        else should_search_live(query)
    )
    catalog_query = shopping_context.product_query or query
    raw_results = await asyncio.to_thread(
        search_fn,
        query=catalog_query,
        price_min=budget_min,
        price_max=budget_max,
        category=category,
        brand=brand,
        k=RAG_CANDIDATE_K,
    )
    relevance_query = shopping_context.product_query or query
    relevant = [
        RagResult.model_validate(item)
        for item in raw_results
        if _is_relevant(relevance_query, item)
    ]
    if not relevant:
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
            resolved_transcript=resolved_transcript,
            decision_source=decision_source,
            shopping_context=shopping_context,
        )

    candidates = [
        ComparisonProduct(private=item, live=None, conflicts=[], match=None)
        for item in relevant
    ]
    candidates = rank_products_by_preferences(
        best_available_facet_pool(candidates, shopping_context),
        shopping_context,
    )
    product = candidates[0].private
    requirements = preference_requirements(shopping_context)
    supported = matched_preferences(
        ComparisonProduct(
            private=product,
            live=None,
            conflicts=[],
            match=None,
        ),
        shopping_context,
    )
    if requirements and len(supported) < max(1, (len(requirements) + 1) // 2):
        return FastReply(
            text=(
                "The closest catalog option doesn’t confirm enough of your "
                "specific preferences, so I’m checking broader web matches "
                "instead of presenting it as a strong fit."
            ),
            product=None,
            citations=(),
            elapsed_ms=int((time.perf_counter() - started) * 1_000),
            live_followup_needed=True,
            turn_kind="web_fallback",
            resolved_transcript=resolved_transcript,
            decision_source=decision_source,
            shopping_context=shopping_context,
        )
    citation = Citation(kind="private", label=product.doc_id, url=None)
    return FastReply(
        text=catalog_recommendation(
            product,
            query=query,
            budget_max=budget_max,
            checking_live=wants_live,
            decisive=delegated,
        ),
        product=product,
        citations=(citation,),
        elapsed_ms=int((time.perf_counter() - started) * 1_000),
        live_followup_needed=wants_live,
        turn_kind=(
            "preference_update"
            if shopping_context.preference_changed
            else "catalog"
        ),
        resolved_transcript=resolved_transcript,
        decision_source=decision_source,
        shopping_context=shopping_context,
    )


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc or url


def warm_fast_reply() -> None:
    """Load catalog metadata and embedding runtime before the first voice turn."""
    _catalog_brands()
    catalog_search(query="product", k=1)
