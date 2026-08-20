"""Conversational preference understanding for multi-turn shopping.

Common attributes are handled locally so routine turns stay fast. Ambiguous,
context-dependent changes can use the project's existing configured LLM once,
with a short timeout and a deterministic fallback. The model only rewrites the
shopper's request; it never supplies product facts.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, Field

from contracts import ComparisonProduct, ShoppingContext
from graph.llm import get_llm, load_prompt
from graph.relevance import infer_catalog_category, normalized_terms


_COLORS = {
    "beige",
    "black",
    "blue",
    "brown",
    "burgundy",
    "clear",
    "cream",
    "gold",
    "gray",
    "green",
    "grey",
    "khaki",
    "multicolor",
    "navy",
    "orange",
    "pink",
    "purple",
    "red",
    "silver",
    "tan",
    "teal",
    "white",
    "yellow",
}
_MATERIALS = {
    "bamboo",
    "canvas",
    "ceramic",
    "cotton",
    "denim",
    "fiberglass",
    "glass",
    "leather",
    "linen",
    "mesh",
    "metal",
    "microfiber",
    "nylon",
    "plastic",
    "polyester",
    "rubber",
    "silicone",
    "stainless steel",
    "steel",
    "suede",
    "wood",
    "wooden",
    "wool",
}
_TEXTURES = {
    "breathable",
    "fleece",
    "fluffy",
    "fuzzy",
    "knit",
    "plush",
    "rough",
    "silky",
    "smooth",
    "soft",
    "stretchy",
    "textured",
    "velvet",
    "waterproof",
}
_COMFORT = {
    "arch support",
    "breathable",
    "comfortable",
    "comfort",
    "cushioned",
    "ergonomic",
    "lightweight",
    "padded",
    "supportive",
    "wide fit",
}
_RELATIVE_SIZES = {
    "adult",
    "california king",
    "compact",
    "extra large",
    "extra small",
    "extra extra large",
    "full",
    "king",
    "large",
    "larger",
    "medium",
    "narrow",
    "one size",
    "queen",
    "small",
    "smaller",
    "tall",
    "twin",
    "twin xl",
    "wide",
    "xl",
    "xs",
    "xxl",
    "youth",
}
_ADULT_AUDIENCE = re.compile(
    r"\b(?:adults?|men|women|unisex)\b",
    re.IGNORECASE,
)
_ADULT_EVIDENCE_TERMS = {"adult", "men", "unisex", "women"}
_CHANGE_CUES = re.compile(
    r"\b(?:actually|also|but|change|different|instead|make (?:it|them)|more|"
    r"less|prefer|rather|switch|need (?:it|them)|want (?:it|them)|with|without)\b",
    re.IGNORECASE,
)
_CONTEXT_PRONOUNS = re.compile(
    r"\b(?:it|its|them|their|those|these|one|ones|something|option|options)\b",
    re.IGNORECASE,
)
_NEW_SEARCH_CUE = re.compile(
    r"^\s*(?:find|show|recommend|search for|i (?:need|want|am looking for)|"
    r"i['’]?m looking for)\b",
    re.IGNORECASE,
)
_NEW_ITEM_TRANSITION_CUE = re.compile(
    r"^\s*(?:"
    r"(?:(?:and\s+)?(?:now|next)|moving\s+on)\s*[,;:—-]?\s*"
    r"(?:(?:i\s+)?(?:need|want|would\s+like|am\s+looking\s+for)|"
    r"(?:let['’]?s\s+)?(?:find|look\s+for|search\s+for|show|recommend))|"
    r"(?:i\s+also|also\s+i)\s+"
    r"(?:need|want|would\s+like|am\s+looking\s+for)"
    r")\b[\s,;:—-]*",
    re.IGNORECASE,
)
_BARE_ALSO_CUE = re.compile(
    r"^\s*also\b[\s,;:—-]*",
    re.IGNORECASE,
)
_NATURAL_NEED_CUE = re.compile(
    r"\b(?:all day|because|doesn['’]?t|for long|matters more|so that|"
    r"something that|won['’]?t|would help|easy on|better for)\b",
    re.IGNORECASE,
)
_INCOMPLETE_FACET_CUE = re.compile(
    r"^\s*(?:change|different|another|switch)\s+(?:the\s+)?"
    r"(?:colou?r|size|material|texture|comfort|feature)\s*$",
    re.IGNORECASE,
)
_CLEAR_BUDGET = re.compile(
    r"\b(?:any price|budget (?:doesn['’]?t|does not) matter|ignore (?:the )?budget|"
    r"no (?:price|budget) limit)\b",
    re.IGNORECASE,
)
_CLEAR_PREFERENCE = re.compile(
    r"\b(?:i\s+)?(?:do\s+not|don['’]?t)\s+care(?:\s+about)?"
    r"(?:\s+(?:any|the))?\s+"
    r"(?P<facet>colou?rs?|sizes?|materials?|textures?|comfort|features?|"
    r"preferences?|details?)\b",
    re.IGNORECASE,
)
_SIZE_PATTERNS = (
    re.compile(r"\bsize\s+(?:of\s+)?([a-z0-9][a-z0-9./ -]{0,14})", re.I),
    re.compile(
        r"\b(\d+(?:\.\d+)?)\s*(inch(?:es)?|in|foot|feet|ft|cm|mm)\b",
        re.I,
    ),
    re.compile(r"\b(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\b", re.I),
)
_GENERIC_FEATURE = re.compile(
    r"\b(?:must have|needs? to (?:have|be)|prefer(?:ably)?|with)\s+"
    r"([^,.;!?]{2,55})",
    re.IGNORECASE,
)
_USE_CASE_FEATURE = re.compile(
    r"\b(?:better for|good for|suitable for|for)\s+([^,.;!?]{2,55})",
    re.IGNORECASE,
)
_RECIPIENT_PHRASE = re.compile(
    r"\b(?:a|an|my|our|the)\s+(?:baby|boy|child|children|daughter|family|father|friend|"
    r"girl|grandchild|granddaughter|grandson|husband|kid|kiddo|kids|mother|"
    r"mom|mum|dad|nephew|niece|parent|parents|partner|son|spouse|toddler|wife)"
    r"\b(?!['’]s\b)(?:\s+please\b)?",
    re.IGNORECASE,
)
_NEGATED_FEATURE = re.compile(
    r"\b(?:anything but|avoid|do not want|don['’]?t want|no|not|without)\s+"
    r"([^,.;!?]{2,35})",
    re.IGNORECASE,
)
_PROFILE_FIELDS = (
    "colors",
    "sizes",
    "materials",
    "textures",
    "comfort",
    "features",
    "excluded",
)
_PRODUCT_PLACEHOLDER_WORDS = {
    "anything",
    "item",
    "items",
    "option",
    "options",
    "product",
    "products",
    "something",
    "stuff",
    "thing",
    "things",
}
_META_REQUEST_WORDS = {
    "ask",
    "asked",
    "asking",
    "request",
    "requested",
    "requesting",
}
_STATIC_FACET_VALUES = (
    _COLORS
    | _MATERIALS
    | _TEXTURES
    | _COMFORT
    | _RELATIVE_SIZES
)
_PRODUCT_USE_CASE_WORDS = {
    "apartment",
    "bathroom",
    "bedroom",
    "home",
    "house",
    "kitchen",
    "office",
    "outdoors",
}
_PRODUCT_NOUN_HINTS = {
    "airpod",
    "backpack",
    "bedding",
    "blanket",
    "book",
    "boot",
    "camera",
    "chair",
    "comforter",
    "computer",
    "dress",
    "duvet",
    "earbud",
    "headphone",
    "hoodie",
    "iphone",
    "jacket",
    "laptop",
    "mattress",
    "phone",
    "pillow",
    "quilt",
    "shirt",
    "shoe",
    "smartphone",
    "sportswear",
    "tablet",
    "television",
    "toy",
    "tv",
}
_TURN_FILLER_WORDS = (
    _PRODUCT_PLACEHOLDER_WORDS
    | _META_REQUEST_WORDS
    | {
        "a",
        "about",
        "an",
        "and",
        "anything",
        "can",
        "could",
        "for",
        "give",
        "i",
        "like",
        "me",
        "my",
        "no",
        "nope",
        "ok",
        "okay",
        "of",
        "on",
        "or",
        "please",
        "sure",
        "some",
        "sounds",
        "the",
        "to",
        "use",
        "want",
        "would",
        "yeah",
        "yep",
        "yes",
        "you",
    }
)
_NOVELTY_GRAMMAR_WORDS = {
    "be",
    "did",
    "didn",
    "do",
    "does",
    "doesn",
    "don",
    "it",
    "its",
    "not",
    "s",
    "t",
}
_FOLLOWUP_FEATURE_TERMS: tuple[tuple[frozenset[str], frozenset[str]], ...] = (
    (
        frozenset({"iphone", "phone", "smartphone"}),
        frozenset(
            {
                "battery",
                "camera",
                "capacity",
                "screen",
                "storage",
            }
        ),
    ),
    (
        frozenset({"boot", "shoe"}),
        frozenset({"arch", "cushion", "support", "traction"}),
    ),
    (
        frozenset({"bedding", "blanket", "comforter", "pillow", "quilt"}),
        frozenset({"cooling", "fill", "warmth"}),
    ),
)
_BROAD_ACTIVE_PRODUCTS = {"gift", "home", "house", "outdoor", "product"}
_BUDGET_ONLY_FOLLOWUP = re.compile(
    r"(?:\$\s*\d|\b(?:under|below|budget|up to|at most|max(?:imum)?)\b)",
    re.IGNORECASE,
)
_ACKNOWLEDGEMENT_ONLY = re.compile(
    r"^\s*(?:yes|yeah|yep|yup|sure|okay|ok|sounds good|please do|go ahead|"
    r"no|nope|not really|maybe|that['’]?s right|that is right|correct|exactly)"
    r"\s*[.!?]*\s*$",
    re.IGNORECASE,
)


class _PreferenceInterpretation(BaseModel):
    action: Literal["refine", "new_search", "not_shopping"]
    product_query: str = ""
    colors: list[str] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    textures: list[str] = Field(default_factory=list)
    comfort: list[str] = Field(default_factory=list)
    features: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)


def _dedupe(values: Iterable[str], *, limit: int = 8) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw or "").strip(" ,.;:-")).casefold()
        if not value or value in seen or len(value) > 60:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def preference_requirements(context: ShoppingContext | dict | None) -> list[str]:
    """Flatten positive facets in a stable, presentation-friendly order."""
    if context is None:
        return []
    profile = (
        context
        if isinstance(context, ShoppingContext)
        else ShoppingContext.model_validate(context)
    )
    return _dedupe(
        value
        for field in _PROFILE_FIELDS[:-1]
        for value in getattr(profile, field)
    )


def preference_summary(context: ShoppingContext | dict | None) -> str:
    """Compact user-preference summary for prompts and step logs."""
    if context is None:
        return ""
    profile = (
        context
        if isinstance(context, ShoppingContext)
        else ShoppingContext.model_validate(context)
    )
    parts = preference_requirements(profile)
    if profile.excluded:
        parts.extend(f"not {value}" for value in profile.excluded)
    return ", ".join(parts)


def clears_budget(transcript: str) -> bool:
    return bool(_CLEAR_BUDGET.search(str(transcript or "")))


def _preference_fields_to_clear(transcript: str) -> set[str]:
    """Map explicit indifference to the facet fields it removes."""
    text = str(transcript or "")
    fields: set[str] = set()
    for match in _CLEAR_PREFERENCE.finditer(text):
        facet = match.group("facet").casefold()
        if facet.startswith("colo"):
            fields.add("colors")
        elif facet.startswith("size"):
            fields.add("sizes")
        elif facet.startswith("material"):
            fields.add("materials")
        elif facet.startswith("texture"):
            fields.add("textures")
        elif facet == "comfort":
            fields.add("comfort")
        elif facet.startswith("feature"):
            fields.update(("comfort", "features"))
        else:
            fields.update(_PROFILE_FIELDS[:-1])
    return fields


def _normalized_facet_terms() -> set[str]:
    return {
        term
        for value in _STATIC_FACET_VALUES
        for term in normalized_terms(value)
    }


def _new_product_terms(transcript: str) -> set[str]:
    terms = normalized_terms(transcript)
    negated_terms = {
        term
        for match in _NEGATED_FEATURE.finditer(transcript)
        for term in normalized_terms(match.group(1))
    }
    return (
        terms
        - _normalized_facet_terms()
        - _TURN_FILLER_WORDS
        - _NOVELTY_GRAMMAR_WORDS
        - negated_terms
    )


def strip_new_product_transition(transcript: str) -> str:
    """Remove a next-item cue while leaving its requested product."""
    text = str(transcript or "")
    explicit = _NEW_ITEM_TRANSITION_CUE.sub(
        "",
        text,
        count=1,
    )
    if explicit != text:
        return explicit.strip()
    return _BARE_ALSO_CUE.sub("", text, count=1).strip()


def _domain_feature_phrase(
    transcript: str,
    previous: ShoppingContext | None,
) -> str:
    if previous is None:
        return ""
    prior_terms = normalized_terms(previous.product_query)
    turn_terms = normalized_terms(transcript)
    if not any(
        prior_terms & product_terms and turn_terms & feature_terms
        for product_terms, feature_terms in _FOLLOWUP_FEATURE_TERMS
    ):
        return ""
    phrase = re.sub(
        r"^\s*(?:a|an|the|i\s+(?:want|prefer|need))\s+",
        "",
        str(transcript or ""),
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", phrase).strip(" ,.;:!?-")


def is_new_product_request(
    transcript: str,
    prior: ShoppingContext | dict | None = None,
) -> bool:
    """Recognize a new product even when the shopper omits "find me".

    Short answers made only of facets remain follow-ups. Named models, obvious
    product nouns, and category phrases reset stale preferences instead.
    """
    text = str(transcript or "").strip()
    if not text:
        return False
    previous = (
        prior
        if isinstance(prior, ShoppingContext)
        else ShoppingContext.model_validate(prior)
        if prior is not None
        else None
    )
    explicit_transition = bool(_NEW_ITEM_TRANSITION_CUE.match(text))
    transition_product = strip_new_product_transition(text)
    if transition_product != text:
        transition_terms = _new_product_terms(transition_product)
        if not transition_terms:
            return False
        if _domain_feature_phrase(transition_product, previous):
            return False
        transition_is_product = bool(
            transition_terms & _PRODUCT_NOUN_HINTS
            or infer_catalog_category(" ".join(sorted(transition_terms)))
        )
        if not explicit_transition and not transition_is_product:
            return False
        if (
            has_actionable_preference(transition_product)
            and not transition_is_product
        ):
            return False
        return True
    meaningful = _new_product_terms(text)
    prior_is_placeholder = bool(
        previous is not None
        and previous.product_query.casefold()
        in {"", "anything", "item", "product", "something", "thing"}
    )
    if previous is not None and _ACKNOWLEDGEMENT_ONLY.fullmatch(text):
        return False
    if _NEW_SEARCH_CUE.search(text):
        # A response such as "I need something for home" completes the
        # assistant's pending clarification and should retain its budget.
        return bool(meaningful) and not prior_is_placeholder
    if prior is None:
        return True
    if _preference_fields_to_clear(text):
        return False
    if _BUDGET_ONLY_FOLLOWUP.search(text):
        return False
    if re.search(r"\b(?:switch to|instead of|rather than)\b", text, re.I):
        return False
    if _CHANGE_CUES.search(text) or _CONTEXT_PRONOUNS.search(text):
        return False
    prior_terms = normalized_terms(previous.product_query) if previous else set()
    if (
        previous is not None
        and has_actionable_preference(text)
        and meaningful
        and meaningful.issubset(prior_terms)
    ):
        return False
    if any(
        prior_terms & product_terms and meaningful & feature_terms
        for product_terms, feature_terms in _FOLLOWUP_FEATURE_TERMS
    ):
        return False
    if previous and previous.product_query.casefold() in _BROAD_ACTIVE_PRODUCTS:
        return False
    if meaningful & _PRODUCT_NOUN_HINTS:
        return True
    if meaningful and infer_catalog_category(" ".join(sorted(meaningful))):
        return True
    # Once explicit facet/change responses have been excluded, a compact noun
    # phrase is much more likely to be the shopper naming another product than
    # answering the previous question. Defaulting it to a new search prevents
    # stale categories and budgets from leaking into unrelated requests.
    return bool(meaningful)


def _phrase_hits(text: str, candidates: Iterable[str]) -> list[str]:
    hits = []
    for value in sorted(candidates, key=len, reverse=True):
        if re.search(rf"\b{re.escape(value)}\b", text, re.IGNORECASE):
            hits.append(value)
    return _dedupe(hits)


def _negated(text: str, value: str) -> bool:
    return bool(
        re.search(
            rf"\b(?:anything but|avoid|do not want|don['’]?t want|no|not|without)"
            rf"(?:\s+\w+){{0,2}}\s+{re.escape(value)}\b",
            text,
            re.IGNORECASE,
        )
    )


def _sizes(text: str) -> list[str]:
    values: list[str] = []
    for pattern in _SIZE_PATTERNS:
        for match in pattern.finditer(text):
            value = " ".join(part for part in match.groups() if part)
            # Stop a loose "size ..." capture before preference connectors.
            value = re.split(
                r"\b(?:and|but|instead|or|with|under|below|over)\b",
                value,
                maxsplit=1,
                flags=re.I,
            )[0]
            value = value.strip()
            if not value:
                continue
            values.append(
                f"size {value}" if pattern is _SIZE_PATTERNS[0] else value
            )
    values.extend(_phrase_hits(text, _RELATIVE_SIZES))
    if _ADULT_AUDIENCE.search(text):
        values.append("adult")
    return _dedupe(values)


def _generic_features(text: str) -> tuple[list[str], list[str]]:
    positive = []
    negative = []
    for match in _GENERIC_FEATURE.finditer(text):
        phrase = re.split(
            r"\b(?:and|but|instead|under|below|over)\b",
            match.group(1),
            maxsplit=1,
            flags=re.I,
        )[0]
        if not re.search(
            r"\b(?:catalog|current|live|price|rating|review|budget|dollars?|bucks?)\b",
            phrase,
            re.I,
        ) and _has_distinct_feature_detail(phrase):
            positive.append(phrase)
    for match in _USE_CASE_FEATURE.finditer(text):
        phrase = re.split(
            r"\b(?:and|but|instead|under|below|over)\b",
            match.group(1),
            maxsplit=1,
            flags=re.I,
        )[0]
        if (
            phrase.casefold().strip() not in {"me", "us", "you"}
            and not _RECIPIENT_PHRASE.fullmatch(phrase.strip())
            and not re.search(
                r"\b(?:catalog|current|live|price|rating|review|budget|dollars?|bucks?)\b",
                phrase,
                re.I,
            )
            and _has_distinct_feature_detail(phrase)
        ):
            positive.append(phrase)
    for match in _NEGATED_FEATURE.finditer(text):
        phrase = re.split(
            r"\b(?:and|but|instead|under|below|over)\b",
            match.group(1),
            maxsplit=1,
            flags=re.I,
        )[0]
        if not re.search(
            r"\b(?:catalog|current|live|price|rating|review|budget|dollars?|bucks?)\b",
            phrase,
            re.I,
        ) and _has_distinct_feature_detail(phrase):
            negative.append(phrase)
    return _dedupe(positive), _dedupe(negative)


def _has_distinct_feature_detail(phrase: str) -> bool:
    """Reject generic-feature captures that contain only a facet and filler."""
    residual = str(phrase or "")
    for value in sorted(_STATIC_FACET_VALUES, key=len, reverse=True):
        residual = re.sub(rf"\b{re.escape(value)}\b", " ", residual, flags=re.I)
    fillers = _PRODUCT_PLACEHOLDER_WORDS | {
        "a",
        "an",
        "be",
        "for",
        "in",
        "of",
        "one",
        "ones",
        "that",
        "the",
        "to",
        "with",
    }
    filler_pattern = "|".join(
        re.escape(word) for word in sorted(fillers, key=len, reverse=True)
    )
    residual = re.sub(rf"\b(?:{filler_pattern})\b", " ", residual, flags=re.I)
    remaining_words = set(re.findall(r"[a-z0-9]+", residual.casefold()))
    return bool(remaining_words) and not remaining_words.issubset(
        _PRODUCT_USE_CASE_WORDS
    )


def _facet_updates(text: str) -> dict[str, list[str]]:
    colors = _phrase_hits(text, _COLORS)
    materials = _phrase_hits(text, _MATERIALS)
    textures = _phrase_hits(text, _TEXTURES)
    comfort = _phrase_hits(text, _COMFORT)
    texture_aliases = {
        "fluffier": "fluffy",
        "plusher": "plush",
        "smoother": "smooth",
        "softer": "soft",
        "stretchier": "stretchy",
    }
    comfort_aliases = {
        "comfier": "comfortable",
        "comfy": "comfortable",
        "comfortability": "comfortable",
        "comfortableness": "comfortable",
        "lighter": "lightweight",
        "more comfortable": "comfortable",
        "more supportive": "supportive",
    }
    textures.extend(
        value
        for alias, value in texture_aliases.items()
        if re.search(rf"\b{re.escape(alias)}\b", text, re.I)
    )
    comfort.extend(
        value
        for alias, value in comfort_aliases.items()
        if re.search(rf"\b{re.escape(alias)}\b", text, re.I)
    )
    textures = _dedupe(textures)
    comfort = _dedupe(comfort)
    sizes = _sizes(text)
    features, generic_excluded = _generic_features(text)
    excluded = list(generic_excluded)
    for value in colors + materials + textures + comfort + sizes:
        if _negated(text, value):
            excluded.append(value)
    return {
        "colors": [value for value in colors if value not in excluded],
        "sizes": [value for value in sizes if value not in excluded],
        "materials": [value for value in materials if value not in excluded],
        "textures": [value for value in textures if value not in excluded],
        "comfort": [value for value in comfort if value not in excluded],
        "features": [value for value in features if value not in excluded],
        "excluded": _dedupe(excluded),
    }


def has_actionable_preference(transcript: str) -> bool:
    """Whether feedback already contains a concrete attribute to search for."""
    text = str(transcript or "")
    updates = _facet_updates(text)
    return bool(_preference_fields_to_clear(text)) or any(
        updates[field] for field in _PROFILE_FIELDS
    )


def is_contextual_followup_candidate(
    transcript: str,
    prior: ShoppingContext | dict | None,
) -> bool:
    """Broad gate for turns that may modify the active shopping request."""
    if prior is None:
        return False
    text = str(transcript or "").strip()
    if not text:
        return False
    if is_new_product_request(text, prior):
        return False
    if has_actionable_preference(text):
        return True
    if _CHANGE_CUES.search(text) or _CONTEXT_PRONOUNS.search(text):
        return True
    # Short fragments after results are usually answers to a question such as
    # "which color/size?"; the LLM can distinguish them from a new search.
    return len(re.findall(r"[a-z0-9]+", text.casefold())) <= 8 and not _NEW_SEARCH_CUE.search(text)


def _normalize_product_family(product_candidate: str, transcript: str) -> str:
    """Collapse spoken lists of interchangeable product types into a family."""
    terms = normalized_terms(transcript)
    bedding_items = terms & {"comforter", "duvet", "pillow", "quilt", "sheet"}
    if (
        "bedding" in terms
        or len(bedding_items) >= 2
        or ("bed" in terms and bedding_items)
    ):
        return "bedding"
    return product_candidate


def _strip_facets(
    clean_query: str,
    updates: dict[str, list[str]],
    transcript: str = "",
) -> str:
    value = clean_query
    phrases = [
        item
        for field in _PROFILE_FIELDS
        for item in updates.get(field, [])
    ]
    for phrase in sorted(phrases, key=len, reverse=True):
        variants = {
            phrase,
            re.sub(r"^(?:a|an|the)\s+", "", phrase, flags=re.I),
        }
        for variant in variants:
            if variant:
                value = re.sub(
                    rf"\b{re.escape(variant)}\b",
                    " ",
                    value,
                    flags=re.I,
                )
    if "adult" in updates.get("sizes", []):
        value = _ADULT_AUDIENCE.sub(" ", value)
    value = _RECIPIENT_PHRASE.sub(" ", value)
    for match in _RECIPIENT_PHRASE.finditer(transcript):
        phrase = match.group(0).strip()
        without_please = re.sub(r"\s+please$", "", phrase, flags=re.I)
        recipient = re.sub(
            r"^(?:a|an|my|our|the)\s+",
            "",
            without_please,
            flags=re.I,
        )
        for variant in {phrase, without_please, recipient, f"{recipient} please"}:
            value = re.sub(
                rf"\b{re.escape(variant)}\b",
                " ",
                value,
                flags=re.I,
            )
    value = re.sub(
        r"\b(?:actually|also|instead|make|more|less|prefer|switch|to|them|those|these|ones?)\b",
        " ",
        value,
        flags=re.I,
    )
    placeholders = _PRODUCT_PLACEHOLDER_WORDS | _META_REQUEST_WORDS
    placeholder_pattern = "|".join(
        re.escape(word) for word in sorted(placeholders, key=len, reverse=True)
    )
    value = re.sub(
        rf"\b(?:{placeholder_pattern})\b",
        " ",
        value,
        flags=re.I,
    )
    if updates.get("excluded"):
        # Facet removal should not leave contrast grammar masquerading as the
        # product family. Limit this cleanup to turns with a parsed exclusion.
        value = re.sub(
            r"\b(?:anything\s+but|avoid|do\s+not\s+want|don['’]?t\s+want|"
            r"does\s+not\s+want|doesn['’]?t\s+want|did\s+not\s+want|"
            r"didn['’]?t\s+want|no|not|without|that['’]?s|that\s+is)\b",
            " ",
            value,
            flags=re.I,
        )
    value = re.sub(r"\s+", " ", value).strip(" ,.;:-")
    return re.sub(r"^(?:in|of|to|with)\s+|\s+(?:in|of|to|with)$", "", value, flags=re.I)


def _compose_query(profile: ShoppingContext) -> str:
    values = [profile.product_query, *preference_requirements(profile)]
    words: list[str] = []
    seen: set[str] = set()
    for value in values:
        for word in str(value).split():
            key = word.casefold().strip(" ,.;:-")
            if key and key not in seen:
                seen.add(key)
                words.append(word.strip(" ,.;:-"))
    return " ".join(words).strip() or profile.product_query or "product"


def with_product_query(
    context: ShoppingContext | dict,
    product_query: str,
    *,
    understanding_source: Literal["rules", "llm", "fallback"] | None = None,
) -> ShoppingContext:
    """Apply an agent-selected product direction without dropping preferences."""
    profile = (
        context
        if isinstance(context, ShoppingContext)
        else ShoppingContext.model_validate(context)
    )
    updated = profile.model_copy(
        update={
            "product_query": str(product_query or "product").strip() or "product",
            "understanding_source": understanding_source or profile.understanding_source,
        },
        deep=True,
    )
    return updated.model_copy(update={"resolved_query": _compose_query(updated)})


def _rule_resolution(
    transcript: str,
    clean_query: str,
    prior: ShoppingContext | dict | None,
) -> ShoppingContext:
    previous = (
        prior
        if isinstance(prior, ShoppingContext)
        else ShoppingContext.model_validate(prior)
        if prior is not None
        else None
    )
    transition_product = strip_new_product_transition(transcript)
    preference_text = (
        transition_product
        if transition_product != str(transcript or "").strip()
        else transcript
    )
    updates = _facet_updates(preference_text)
    inferred_domain_feature = _domain_feature_phrase(preference_text, previous)
    if inferred_domain_feature and not any(
        updates[field] for field in _PROFILE_FIELDS
    ):
        updates["features"] = [inferred_domain_feature.casefold()]
    contextual = is_contextual_followup_candidate(transcript, previous)
    product_candidate = _normalize_product_family(
        _strip_facets(clean_query, updates, transcript),
        transcript,
    )
    explicit_new = is_new_product_request(transcript, previous)
    if previous is None or explicit_new:
        base = ShoppingContext(product_query=product_candidate or "product")
        contextual = False
    else:
        base = previous.model_copy(deep=True)
        prior_accepts_direction = previous.product_query.casefold() in {
            "",
            "anything",
            "gift",
            "home",
            "house",
            "item",
            "outdoor",
            "product",
            "something",
            "thing",
        }
        if prior_accepts_direction and product_candidate.casefold() not in {
            "",
            "anything",
            "item",
            "product",
            "something",
            "thing",
        }:
            base = previous.model_copy(
                update={"product_query": product_candidate},
                deep=True,
            )
            contextual = True
        # "switch to boots" and "boots instead" replace the product while
        # ordinary attribute fragments retain the active product.
        replacing_product = bool(
            re.search(r"\b(?:switch to|instead of|rather than)\b", transcript, re.I)
            or (
                re.search(r"\binstead\b", transcript, re.I)
                and product_candidate
                and not has_actionable_preference(transcript)
            )
        )
        if replacing_product and product_candidate:
            base = ShoppingContext(product_query=product_candidate)
            contextual = True

    data = base.model_dump()
    for field in _PROFILE_FIELDS[:-1]:
        values = updates[field]
        if not values:
            continue
        # Color, size, material, and texture changes replace the previous
        # value unless the shopper explicitly says "also".
        replace = field in {"colors", "sizes", "materials", "textures"} and not re.search(
            r"\balso\b", transcript, re.I
        )
        data[field] = _dedupe(values if replace else [*data[field], *values])
    if updates["excluded"]:
        data["excluded"] = _dedupe([*data["excluded"], *updates["excluded"]])
        for field in _PROFILE_FIELDS[:-1]:
            data[field] = [
                item for item in data[field] if item not in data["excluded"]
            ]

    clear_checks = {
        "colors": r"\b(?:any|no) colou?r(?: preference)?\b",
        "sizes": r"\b(?:any|no) size(?: preference)?\b",
        "materials": r"\b(?:any|no) material(?: preference)?\b",
        "textures": r"\b(?:any|no) texture(?: preference)?\b",
    }
    for field, pattern in clear_checks.items():
        if re.search(pattern, transcript, re.I):
            data[field] = []
    for field in _preference_fields_to_clear(transcript):
        data[field] = []

    data["is_followup"] = contextual
    comparable_fields = ("product_query", *_PROFILE_FIELDS)
    data["preference_changed"] = bool(
        contextual
        and previous is not None
        and any(data[field] != getattr(previous, field) for field in comparable_fields)
    )
    data["understanding_source"] = "rules"
    provisional = ShoppingContext.model_validate(data)
    return provisional.model_copy(update={"resolved_query": _compose_query(provisional)})


def _llm_is_configured() -> bool:
    if os.getenv("PREFERENCE_LLM", "1").strip().lower() in {"0", "false", "off"}:
        return False
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    key_name = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    return bool(os.getenv(key_name, "").strip())


def _needs_llm(
    transcript: str,
    profile: ShoppingContext,
    prior: ShoppingContext | dict | None,
) -> bool:
    if not _llm_is_configured():
        return False
    if _INCOMPLETE_FACET_CUE.search(transcript):
        return False
    # Rules can safely preserve the active product for a bare acknowledgement.
    # The dialogue call then uses the previous assistant question to phrase one
    # contextual response, avoiding two sequential model calls for “yes/no”.
    if prior is not None and _ACKNOWLEDGEMENT_ONLY.fullmatch(transcript):
        return False
    return bool(
        _NATURAL_NEED_CUE.search(transcript)
        or (
            prior is not None
            and is_contextual_followup_candidate(transcript, prior)
            and not has_actionable_preference(transcript)
            and not profile.preference_changed
        )
    )


def _from_llm(
    output: _PreferenceInterpretation,
    fallback: ShoppingContext,
) -> ShoppingContext:
    if output.action == "not_shopping":
        return fallback
    data = {
        "product_query": output.product_query.strip() or fallback.product_query,
        "colors": _dedupe(output.colors),
        "sizes": _dedupe(output.sizes),
        "materials": _dedupe(output.materials),
        "textures": _dedupe(output.textures),
        "comfort": _dedupe(output.comfort),
        "features": _dedupe(output.features),
        "excluded": _dedupe(output.excluded),
        "resolved_query": "",
        "is_followup": output.action == "refine",
        "preference_changed": False,
        "understanding_source": "llm",
    }
    profile = ShoppingContext.model_validate(data)
    changed = bool(
        output.action == "refine"
        and (
            fallback.preference_changed
            or any(
                getattr(profile, field) != getattr(fallback, field)
                for field in ("product_query", *_PROFILE_FIELDS)
            )
        )
    )
    return profile.model_copy(
        update={
            "resolved_query": _compose_query(profile),
            "preference_changed": changed,
        }
    )


async def resolve_preferences(
    transcript: str,
    clean_query: str,
    prior: ShoppingContext | dict | None = None,
    *,
    previous_answer: str = "",
    allow_llm: bool = True,
    llm_factory=get_llm,
) -> ShoppingContext:
    """Resolve a complete search profile, preserving or replacing prior facets."""
    fallback = _rule_resolution(transcript, clean_query, prior)
    if not allow_llm or not _needs_llm(transcript, fallback, prior):
        return fallback

    previous = (
        prior.model_dump(mode="json")
        if isinstance(prior, ShoppingContext)
        else prior or {}
    )
    human = (
        "<previous_preferences>\n"
        + json.dumps(previous, ensure_ascii=False)
        + "\n</previous_preferences>\n"
        + "<previous_assistant_answer>\n"
        + str(previous_answer or "none")
        + "\n</previous_assistant_answer>\n"
        + "<shopper_turn>\n"
        + str(transcript)
        + "\n</shopper_turn>\n"
        + f"Rule-based fallback query: {fallback.resolved_query!r}"
    )
    try:
        llm = llm_factory().with_structured_output(_PreferenceInterpretation)
        timeout = max(0.5, float(os.getenv("PREFERENCE_LLM_TIMEOUT_S", "6.0")))
        output = await asyncio.wait_for(
            llm.ainvoke(
                [("system", load_prompt("preferences")), ("human", human)]
            ),
            timeout=timeout,
        )
        return _from_llm(output, fallback)
    except Exception:
        return fallback.model_copy(update={"understanding_source": "fallback"})


def _product_evidence_text(product: ComparisonProduct) -> str:
    parts: list[str] = []
    if product.private is not None:
        parts.append(product.private.title)
        parts.extend(product.private.feature_evidence)
    if product.live is not None:
        parts.extend((product.live.title, product.live.snippet))
    return " ".join(parts)


def matched_preferences(
    product: ComparisonProduct,
    context: ShoppingContext | dict | None,
) -> list[str]:
    """Return shopper requirements explicitly supported by product evidence."""
    evidence_text = _product_evidence_text(product)
    evidence_terms = normalized_terms(evidence_text)
    matched = []
    for requirement in preference_requirements(context):
        terms = normalized_terms(requirement)
        size_match = re.fullmatch(r"size\s+(.+)", requirement, re.I)
        if requirement == "adult":
            supported = bool(evidence_terms & _ADULT_EVIDENCE_TERMS)
        elif size_match:
            size_value = size_match.group(1).strip()
            if re.fullmatch(r"\d+(?:\.\d+)?", size_value):
                supported = bool(
                    re.search(
                        rf"\bsize\s*[:#-]?\s*{re.escape(size_value)}\b|"
                        rf"\b{re.escape(size_value)}\s*(?:us|uk|eu)\s+size\b",
                        evidence_text,
                        re.I,
                    )
                )
            else:
                supported = bool(terms) and terms.issubset(evidence_terms)
        else:
            supported = bool(terms) and terms.issubset(evidence_terms)
        if supported:
            matched.append(requirement)
    return matched


def filter_products_by_required_facets(
    products: list[ComparisonProduct],
    context: ShoppingContext | dict | None,
) -> list[ComparisonProduct]:
    """Keep products that evidence every explicit hard-facet group.

    Values within one group are alternatives (for example blue *or* navy),
    while color, size, material, and texture groups must each be represented.
    Comfort and free-form features remain soft ranking signals because their
    wording is often subjective or absent from otherwise useful evidence.
    """
    if not products or context is None:
        return products
    profile = (
        context
        if isinstance(context, ShoppingContext)
        else ShoppingContext.model_validate(context)
    )
    hard_groups = tuple(
        tuple(getattr(profile, field))
        for field in ("colors", "sizes", "materials", "textures")
        if getattr(profile, field)
    )
    if not hard_groups and not profile.excluded:
        return products

    kept = []
    for product in products:
        matched = set(matched_preferences(product, profile))
        evidence_terms = normalized_terms(_product_evidence_text(product))
        contradicted = any(
            (terms := normalized_terms(value)) and terms.issubset(evidence_terms)
            for value in profile.excluded
        )
        if contradicted:
            continue
        if all(any(value in matched for value in group) for group in hard_groups):
            kept.append(product)
    return kept


def rank_products_by_preferences(
    products: list[ComparisonProduct],
    context: ShoppingContext | dict | None,
) -> list[ComparisonProduct]:
    """Put the best evidenced requirement coverage first without fabricating fit."""
    if not products or context is None:
        return products
    profile = (
        context
        if isinstance(context, ShoppingContext)
        else ShoppingContext.model_validate(context)
    )
    requirements = preference_requirements(profile)
    excluded_terms = [normalized_terms(value) for value in profile.excluded]

    def score(index_product: tuple[int, ComparisonProduct]) -> tuple[float, float, int]:
        index, product = index_product
        evidence_terms = normalized_terms(_product_evidence_text(product))
        matched = len(matched_preferences(product, profile))
        contradiction = sum(
            bool(terms) and terms.issubset(evidence_terms)
            for terms in excluded_terms
        )
        similarity = (
            float(product.private.similarity)
            if product.private is not None
            else 0.0
        )
        coverage = matched / max(len(requirements), 1)
        return (coverage - (2.0 * contradiction), similarity, -index)

    return [
        product
        for _, product in sorted(
            enumerate(products),
            key=score,
            reverse=True,
        )
    ]
