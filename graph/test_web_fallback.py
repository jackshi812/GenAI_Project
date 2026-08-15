"""Regression tests for direct web fallback after weak catalog retrieval."""

from __future__ import annotations

import unittest

from contracts import RagResult, WebResult
from graph.retriever import make_retriever_node


class _Tools:
    async def rag_search(self, query: str, **filters) -> list[RagResult]:
        return [
            RagResult(
                sku="toy-food",
                title="Learning Resources Pretend Food Basket",
                price=13.99,
                rating=None,
                brand="Learning Resources",
                ingredients=None,
                doc_id="CAT-TOY",
                image_url="https://example.com/toy.jpg",
                product_url="https://example.com/toy",
                category="Toys & Games",
                price_low=13.99,
                price_high=13.99,
                similarity=0.8,
                budget_fit="within",
            )
        ]

    async def web_search(self, query: str, num: int = 10) -> list[WebResult]:
        return [
            WebResult(
                title="Fresh Grocery Pantry Box",
                url="https://www.walmart.com/search?q=pantry+box",
                snippet="Walmart",
                price=18.0,
                availability="Delivery",
                rating=4.4,
                origin="live_serper",
            ),
            WebResult(
                title="Premium Grocery Basket",
                url="https://www.amazon.com/s?k=grocery+basket",
                snippet="Amazon",
                price=35.0,
                availability=None,
                rating=None,
                origin="live_serper",
            ),
        ]


class WebFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_weak_catalog_result_falls_back_to_budgeted_web_products(self) -> None:
        node = make_retriever_node(_Tools())
        result = await node(
            {
                "use_private": True,
                "use_live": False,
                "semantic_query": "groceries",
                "filters": {"price_max": 20.0, "k": 5},
            }
        )

        self.assertEqual(result["rag_results"], [])
        self.assertEqual(len(result["products"]), 1)
        self.assertIsNone(result["products"][0].private)
        self.assertEqual(result["products"][0].live.price, 18.0)
        self.assertTrue(
            any(step.tool == "web.search" for step in result["steps"])
        )


if __name__ == "__main__":
    unittest.main()
