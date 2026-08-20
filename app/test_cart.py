"""Regression tests for the session-local grounded product cart."""

from __future__ import annotations

import unittest

from app.cart import (
    add_to_cart,
    canonical_product_key,
    clear_cart,
    is_in_cart,
    remove_from_cart,
)
from contracts import ComparisonProduct, RagResult, WebResult


def _catalog_product(
    doc_id: str,
    *,
    title: str | None = None,
    live: WebResult | None = None,
) -> ComparisonProduct:
    private = RagResult(
        sku=f"sku-{doc_id}",
        title=title or f"Catalog {doc_id}",
        price=12.5,
        rating=None,
        brand="Grounded Brand",
        ingredients=None,
        doc_id=doc_id,
        image_url="https://example.com/catalog.jpg",
        product_url=f"https://example.com/catalog/{doc_id}",
        category="Home & Kitchen",
        price_low=12.5,
        price_high=12.5,
        similarity=0.9,
        budget_fit="within",
    )
    return ComparisonProduct(
        private=private,
        live=live,
        conflicts=[],
        match=None,
    )


def _live_product(url: str, *, title: str = "Live product") -> ComparisonProduct:
    return ComparisonProduct(
        private=None,
        live=WebResult(
            title=title,
            url=url,
            snippet="Grounded retailer result.",
            price=18.75,
            availability="In stock",
            image_url="https://example.com/live.jpg",
            rating=4.6,
            origin="live_serper",
        ),
        conflicts=[],
        match=None,
    )


class CartStateTests(unittest.TestCase):
    def test_canonical_identity_prefers_catalog_and_supports_live_only(self) -> None:
        matched = _catalog_product(
            "CAT-001",
            live=_live_product("https://retailer.example/item").live,
        )
        live_only = _live_product("https://retailer.example/live-only")

        self.assertEqual(canonical_product_key(matched), "catalog:CAT-001")
        self.assertEqual(
            canonical_product_key(live_only),
            "live:https://retailer.example/live-only",
        )

    def test_add_appends_distinct_snapshots_without_mutating_the_caller(self) -> None:
        first = _catalog_product("CAT-001")
        second = _live_product("https://retailer.example/second")
        original: list[ComparisonProduct] = []

        after_first = add_to_cart(original, first)
        after_second = add_to_cart(after_first, second)

        self.assertEqual(original, [])
        self.assertEqual(after_first, [first])
        self.assertEqual(after_second, [first, second])
        self.assertIs(after_second[0], first)
        self.assertIs(after_second[1], second)

    def test_duplicate_add_is_a_noop_that_keeps_the_first_snapshot_and_order(self) -> None:
        retained = _catalog_product("CAT-001", title="Original grounded title")
        second = _catalog_product("CAT-002")
        newer_snapshot = _catalog_product(
            "CAT-001",
            title="Later title for the same catalog document",
            live=_live_product("https://retailer.example/newer").live,
        )
        cart = [retained, second]

        updated = add_to_cart(cart, newer_snapshot)

        self.assertIsNot(updated, cart)
        self.assertEqual(updated, cart)
        self.assertIs(updated[0], retained)
        self.assertNotEqual(updated[0], newer_snapshot)
        self.assertTrue(is_in_cart(updated, newer_snapshot))

    def test_remove_targets_one_key_and_preserves_remaining_relative_order(self) -> None:
        first = _catalog_product("CAT-001")
        middle = _live_product("https://retailer.example/middle")
        last = _catalog_product("CAT-003")
        cart = [first, middle, last]

        updated = remove_from_cart(cart, canonical_product_key(middle))

        self.assertEqual(cart, [first, middle, last])
        self.assertEqual(updated, [first, last])
        self.assertFalse(is_in_cart(updated, middle))
        self.assertTrue(is_in_cart(updated, first))

    def test_clear_returns_a_new_empty_cart_without_mutating_input(self) -> None:
        item = _catalog_product("CAT-001")
        cart = [item]

        cleared = clear_cart(cart)

        self.assertEqual(cleared, [])
        self.assertIsNot(cleared, cart)
        self.assertEqual(cart, [item])


if __name__ == "__main__":
    unittest.main()
