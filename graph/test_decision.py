"""Tests for constrained LLM shopping decisions."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from contracts import ComparisonProduct, RagResult
from graph.decision import choose_direction, choose_product_index


class _StructuredLLM:
    def __init__(self, response) -> None:
        self.response = response

    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, _messages):
        return self.response


def _product(title: str, doc_id: str) -> ComparisonProduct:
    private = RagResult(
        sku=doc_id,
        title=title,
        price=12.0,
        rating=None,
        brand=None,
        ingredients=None,
        doc_id=doc_id,
        image_url="https://example.com/image.jpg",
        product_url="https://example.com/product",
        category="Toys & Games",
        price_low=12.0,
        price_high=12.0,
        similarity=0.9,
        budget_fit="within",
    )
    return ComparisonProduct(private=private, live=None, conflicts=[], match=None)


class DecisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_llm_selects_only_an_eligible_catalog_direction(self) -> None:
        direction = await choose_direction(
            "I don't know, help me decide",
            {"avoid_categories": ["Toys & Games"]},
            llm_factory=lambda: _StructuredLLM(
                SimpleNamespace(option_id="outdoor_basketball")
            ),
        )

        self.assertEqual(direction.query, "basketball")
        self.assertEqual(direction.category, "Sports & Outdoors")
        self.assertEqual(direction.selected_by, "llm")

    async def test_unavailable_llm_uses_a_non_rejected_grounded_fallback(self) -> None:
        def fail():
            raise RuntimeError("model unavailable")

        direction = await choose_direction(
            "Surprise me",
            {"avoid_categories": ["Toys & Games"]},
            llm_factory=fail,
        )

        self.assertEqual(direction.query, "storage")
        self.assertEqual(direction.category, "Home & Kitchen")
        self.assertEqual(direction.selected_by, "fallback")

    async def test_llm_can_choose_among_prior_grounded_products(self) -> None:
        products = [_product("Puzzle One", "ONE"), _product("Puzzle Two", "TWO")]
        index, source = await choose_product_index(
            "Help me decide",
            products,
            llm_factory=lambda: _StructuredLLM(
                SimpleNamespace(candidate_number=2)
            ),
        )

        self.assertEqual(index, 1)
        self.assertEqual(source, "llm")


if __name__ == "__main__":
    unittest.main()
