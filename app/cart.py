"""Pure ordered state operations for the session-local grounded product cart."""

from __future__ import annotations

from collections.abc import Sequence

from contracts import ComparisonProduct


def canonical_product_key(product: ComparisonProduct) -> str:
    """Return the graph-compatible identity for one grounded product snapshot."""
    if product.private is not None:
        return f"catalog:{product.private.doc_id}"
    if product.live is not None:
        return f"live:{product.live.url}"
    return ""


def _target_key(product_or_key: ComparisonProduct | str) -> str:
    if isinstance(product_or_key, str):
        return product_or_key
    return canonical_product_key(product_or_key)


def is_in_cart(
    cart_products: Sequence[ComparisonProduct],
    product_or_key: ComparisonProduct | str,
) -> bool:
    """Return whether a grounded identity is already retained in the cart."""
    target_key = _target_key(product_or_key)
    if not target_key:
        return False
    return any(
        canonical_product_key(product) == target_key
        for product in cart_products
    )


def add_to_cart(
    cart_products: Sequence[ComparisonProduct],
    product: ComparisonProduct,
) -> list[ComparisonProduct]:
    """Append a new identity while preserving the first retained snapshot."""
    if not canonical_product_key(product):
        raise ValueError("cart products require catalog or live evidence")
    retained = list(cart_products)
    if is_in_cart(retained, product):
        return retained
    return [*retained, product]


def remove_from_cart(
    cart_products: Sequence[ComparisonProduct],
    product_or_key: ComparisonProduct | str,
) -> list[ComparisonProduct]:
    """Remove only the requested identity without reordering other snapshots."""
    target_key = _target_key(product_or_key)
    if not target_key:
        return list(cart_products)
    return [
        product
        for product in cart_products
        if canonical_product_key(product) != target_key
    ]


def clear_cart(
    cart_products: Sequence[ComparisonProduct],
) -> list[ComparisonProduct]:
    """Return a fresh empty cart without mutating the caller's collection."""
    return []
