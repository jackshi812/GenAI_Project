"""Shared lexical relevance checks for catalog retrieval."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection
from typing import Any


GROCERY_TERMS = {
    "broccoli",
    "food",
    "fruit",
    "grocery",
    "lettuce",
    "produce",
    "snack",
    "vegetable",
}

_CATEGORY_CUES: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "Home & Kitchen",
        frozenset(
            {
                "apartment",
                "bathroom",
                "bed",
                "bedding",
                "bedroom",
                "comforter",
                "cookware",
                "decor",
                "duvet",
                "home",
                "house",
                "kitchen",
                "organizer",
                "pillow",
                "quilt",
                "sheet",
                "storage",
            }
        ),
    ),
    (
        "Clothing, Shoes & Jewelry",
        frozenset(
            {
                "apparel",
                "clothes",
                "clothing",
                "dress",
                "jacket",
                "jewelry",
                "shirt",
                "shoe",
                "sportswear",
                "wear",
            }
        ),
    ),
    (
        "Sports & Outdoors",
        frozenset(
            {
                "basketball",
                "camping",
                "exercise",
                "fitness",
                "outdoor",
                "sport",
                "workout",
            }
        ),
    ),
    (
        "Toys & Games",
        frozenset({"craft", "game", "puzzle", "toy"}),
    ),
    ("Grocery & Gourmet Food", frozenset(GROCERY_TERMS)),
)


def normalized_terms(value: str, stopwords: Collection[str] = ()) -> set[str]:
    """Normalize accents and simple plurals for transparent title matching."""
    folded = unicodedata.normalize("NFKD", str(value))
    ascii_value = folded.encode("ascii", "ignore").decode("ascii").casefold()

    def normalize(term: str) -> str:
        if term.endswith("ies") and len(term) > 4:
            return f"{term[:-3]}y"
        if term.endswith("s") and len(term) > 3:
            return term[:-1]
        return term

    return {
        normalize(term)
        for term in re.findall(r"[a-z0-9]+", ascii_value)
        if term not in stopwords
    }


def infer_catalog_category(value: str) -> str | None:
    """Map an obvious product or use-case phrase to the catalog taxonomy."""
    terms = normalized_terms(value)
    matches = [
        (len(terms & cues), category)
        for category, cues in _CATEGORY_CUES
        if terms & cues
    ]
    return max(matches, default=(0, None), key=lambda item: item[0])[1]


def _value(result: Any, name: str, default=None):
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def catalog_result_is_relevant(
    query: str,
    result: Any,
    *,
    stopwords: Collection[str] = (),
) -> bool:
    """Reject semantically nearby products that do not satisfy the words asked."""
    query_terms = normalized_terms(query, stopwords)
    title_terms = normalized_terms(str(_value(result, "title", "")), stopwords)
    feature_terms = normalized_terms(
        " ".join(str(item) for item in (_value(result, "feature_evidence", []) or [])),
        stopwords,
    )
    evidence_terms = title_terms | feature_terms
    if not query_terms:
        return False
    overlap = len(query_terms & evidence_terms)
    coverage = overlap / len(query_terms)
    similarity = float(_value(result, "similarity", 0.0) or 0.0)
    if query_terms & GROCERY_TERMS and _value(result, "category") != (
        "Grocery & Gourmet Food"
    ):
        return False
    return (
        coverage >= 0.8
        or (coverage >= 0.6 and similarity >= 0.4)
        or (overlap >= 1 and similarity >= 0.55)
    )
