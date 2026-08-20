"""Canonical, graph-owned top recommendation identity and grounded rationale."""

from __future__ import annotations

import re

from contracts import ComparisonProduct, TopRecommendation
from graph.preferences import matched_preferences, preference_requirements


def product_identity(product: ComparisonProduct) -> str:
    """Return the stable evidence identity used across graph and interface."""
    if product.private is not None:
        return f"catalog:{product.private.doc_id}"
    if product.live is not None:
        return f"live:{product.live.url}"
    return ""


def product_title(product: ComparisonProduct) -> str:
    if product.live is not None:
        return product.live.title
    if product.private is not None:
        return product.private.title
    return "Product"


def canonicalize_products(
    products: list[ComparisonProduct],
    selected_index: int = 0,
) -> list[ComparisonProduct]:
    """Move the graph-selected product to index zero without losing alternatives."""
    if not products:
        return []
    index = min(max(int(selected_index), 0), len(products) - 1)
    if index == 0:
        return list(products)
    return [products[index], *products[:index], *products[index + 1 :]]


def _known_price(product: ComparisonProduct) -> tuple[float | None, str]:
    live_price = product.live.price if product.live is not None else None
    if isinstance(live_price, (int, float)) and not isinstance(live_price, bool):
        source = (
            "current web price"
            if product.live.origin == "live_serper"
            else "recorded web price"
            if product.live.origin == "recorded_fixture"
            else "web price"
        )
        return float(live_price), source
    if product.private is not None:
        value = product.private.price_low
        if value is None and isinstance(product.private.price, (int, float)):
            value = float(product.private.price)
        if value is not None:
            return float(value), "2020 catalog price"
    return None, ""


def _compact(value: str, word_limit: int = 12) -> str:
    words = re.sub(r"\s+", " ", str(value or "").strip()).split()
    return " ".join(words[:word_limit]).rstrip(" ,;:-")


def _compact_feature_detail(
    value: str,
    word_limit: int = 12,
    hard_word_limit: int = 16,
) -> str:
    """Keep short evidence whole and compact longer text at source punctuation."""
    words = re.sub(r"\s+", " ", str(value or "").strip()).split()
    if len(words) <= hard_word_limit:
        return " ".join(words).rstrip(" ,;:-")

    capped = words[:hard_word_limit]
    minimum_clause_words = max(4, word_limit // 2)
    clause_ends = []
    for index, word in enumerate(capped, start=1):
        if index >= minimum_clause_words and re.search(
            r"[,;:.!?][\"')\]]*$",
            word,
        ):
            clause_ends.append(index)
    if not clause_ends:
        return ""
    preferred_ends = [index for index in clause_ends if index <= word_limit]
    clause_end = preferred_ends[-1] if preferred_ends else clause_ends[0]
    return " ".join(capped[:clause_end]).rstrip(" ,;:-")


def recommendation_reason(product: ComparisonProduct, state: dict) -> str:
    """Explain the rank with evidence, never by echoing the shopper's query."""
    constraints = state.get("constraints") or {}
    budget_min = constraints.get("budget_min")
    budget_max = constraints.get("budget_max")
    context = state.get("shopping_context")
    supported = matched_preferences(product, context)
    requirements = preference_requirements(context)
    unconfirmed = [value for value in requirements if value not in supported]
    if "adult" in unconfirmed:
        return ""
    if product.private is not None and product.private.feature_evidence:
        detail = _compact_feature_detail(product.private.feature_evidence[0])
        if detail:
            suffix = "" if re.search(r"[.!?][\"')\]]*$", detail) else "."
            return f"Catalog evidence notes: {detail}{suffix}"

    price, source = _known_price(product)
    if price is not None and budget_min is not None and budget_max is not None:
        if float(budget_min) <= price <= float(budget_max):
            return (
                f"Its {source} is ${price:,.2f}, within your "
                f"${float(budget_min):g}–${float(budget_max):g} range."
            )
    if price is not None and budget_max is not None and price <= float(budget_max):
        return (
            f"Its {source} is ${price:,.2f} and fits your "
            f"${float(budget_max):g} budget."
        )
    if price is not None and budget_min is not None and price >= float(budget_min):
        return (
            f"Its {source} is ${price:,.2f}, above your "
            f"${float(budget_min):g} minimum."
        )
    if supported:
        compact_supported = [_compact(value, 2) for value in supported[:2]]
        return "Grounded evidence confirms " + ", ".join(compact_supported) + "."
    if price is not None:
        return f"Its {source} is ${price:,.2f}."
    return ""


def build_top_recommendation(
    products: list[ComparisonProduct],
    state: dict,
) -> TopRecommendation | None:
    """Create metadata only when products[0] has a traceable source identity."""
    if not products:
        return None
    product = products[0]
    identity = product_identity(product)
    if not identity:
        return None
    return TopRecommendation(
        product_key=identity,
        title=product_title(product),
        reason=recommendation_reason(product, state),
    )
