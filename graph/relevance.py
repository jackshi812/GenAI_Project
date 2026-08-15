"""Shared lexical relevance checks for catalog retrieval."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection
from typing import Any


GROCERY_TERMS = {"food", "grocery", "snack"}


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
    if not query_terms:
        return False
    overlap = len(query_terms & title_terms)
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
