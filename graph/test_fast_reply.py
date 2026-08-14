"""Regression tests for the sub-three-second grounded first-response path."""

from __future__ import annotations

import asyncio
import unittest

from graph.fast_reply import (
    build_fast_reply,
    extract_brand,
    extract_budget_max,
    semantic_query,
)


def _catalog_result(*, budget_fit: str = "within") -> dict:
    return {
        "sku": "nerf-1",
        "title": "Nerf N-Strike Elite Strongarm Toy Blaster with Rotating Barrel",
        "price": 13.99,
        "rating": None,
        "brand": "Nerf",
        "ingredients": None,
        "doc_id": "CAT-00001",
        "image_url": "https://example.com/image.jpg",
        "product_url": "https://example.com/product",
        "category": "Toys & Games",
        "price_low": 13.99,
        "price_high": 13.99,
        "similarity": 0.9,
        "budget_fit": budget_fit,
    }


class FastReplyTests(unittest.TestCase):
    def test_extracts_numeric_and_spoken_budgets(self) -> None:
        self.assertEqual(extract_budget_max("Find a puzzle under $20"), 20.0)
        self.assertEqual(
            extract_budget_max("Find a puzzle under twenty dollars"), 20.0
        )
        self.assertEqual(
            extract_budget_max("Find a toy below one thousand dollars"), 1_000.0
        )

    def test_semantic_query_removes_budget_and_routing_words(self) -> None:
        self.assertEqual(
            semantic_query("Please find me a current Nerf blaster under $20"),
            "Nerf blaster",
        )

    def test_brand_filter_uses_only_known_catalog_brand(self) -> None:
        self.assertEqual(extract_brand("Find me a Nerf blaster"), "Nerf")
        self.assertIsNone(extract_brand("Find me a TotallyInventedBrand blaster"))

    def test_live_request_gets_grounded_catalog_answer_then_followup(self) -> None:
        calls = []

        def fake_search(**kwargs):
            calls.append(kwargs)
            return [_catalog_result()]

        reply = asyncio.run(
            build_fast_reply(
                "Compare the current Nerf blaster price under $20",
                search_fn=fake_search,
            )
        )

        self.assertEqual(calls[0]["query"], "Nerf blaster")
        self.assertEqual(calls[0]["price_max"], 20.0)
        self.assertEqual(calls[0]["brand"], "Nerf")
        self.assertIn("$13.99", reply.text)
        self.assertIn("2020 catalog", reply.text)
        self.assertLessEqual(len(reply.text.split()), 16)
        self.assertNotIn("with Rotating", reply.text)
        self.assertNotIn("Top pick", reply.text)
        self.assertTrue(reply.live_followup_needed)
        self.assertEqual(reply.citations[0].label, "CAT-00001")

    def test_private_budget_request_says_it_fits(self) -> None:
        reply = asyncio.run(
            build_fast_reply(
                "Find a Nerf blaster under twenty dollars",
                search_fn=lambda **_: [_catalog_result()],
            )
        )
        self.assertIn("fits your $20 budget", reply.text)
        self.assertFalse(reply.live_followup_needed)

    def test_no_match_does_not_invent_a_product(self) -> None:
        reply = asyncio.run(
            build_fast_reply("Find a moon car", search_fn=lambda **_: [])
        )
        self.assertIsNone(reply.product)
        self.assertEqual(reply.citations, ())
        self.assertIn("couldn’t find", reply.text)


if __name__ == "__main__":
    unittest.main()
