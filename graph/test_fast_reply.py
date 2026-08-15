"""Regression tests for the sub-three-second grounded first-response path."""

from __future__ import annotations

import asyncio
import unittest

from graph.fast_reply import (
    build_fast_reply,
    conversation_reply,
    extract_brand,
    extract_budget_max,
    semantic_query,
)


def _catalog_result(
    *,
    budget_fit: str = "within",
    title: str = "Nerf N-Strike Elite Strongarm Toy Blaster with Rotating Barrel",
    category: str = "Toys & Games",
    similarity: float = 0.9,
) -> dict:
    return {
        "sku": "nerf-1",
        "title": title,
        "price": 13.99,
        "rating": None,
        "brand": "Nerf",
        "ingredients": None,
        "doc_id": "CAT-00001",
        "image_url": "https://example.com/image.jpg",
        "product_url": "https://example.com/product",
        "category": category,
        "price_low": 13.99,
        "price_high": 13.99,
        "similarity": similarity,
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

    def test_semantic_query_removes_greeting_from_shopping_request(self) -> None:
        self.assertEqual(
            semantic_query("Hello, I need vegetables like broccoli and lettuce"),
            "vegetables broccoli lettuce",
        )

    def test_brand_filter_requires_an_explicit_brand_cue(self) -> None:
        self.assertEqual(extract_brand("Find a blaster by Nerf"), "Nerf")
        self.assertIsNone(extract_brand("Find me a Nerf blaster"))
        self.assertIsNone(extract_brand("What can I buy under $20?"))
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
        self.assertIsNone(calls[0]["brand"])
        self.assertIsNone(calls[0]["category"])
        self.assertIn("$13.99", reply.text)
        self.assertIn("2020 catalog", reply.text)
        self.assertLessEqual(len(reply.text.split()), 19)
        self.assertNotIn("with Rotating", reply.text)
        self.assertNotIn("Top pick", reply.text)
        self.assertTrue(reply.live_followup_needed)
        self.assertEqual(reply.citations[0].label, "CAT-00001")

    def test_named_product_automatically_checks_current_listings(self) -> None:
        reply = asyncio.run(
            build_fast_reply(
                "Find a Nerf blaster under twenty dollars",
                search_fn=lambda **_: [_catalog_result()],
            )
        )
        self.assertIn("checking current listings", reply.text)
        self.assertTrue(reply.live_followup_needed)

    def test_broad_catalog_request_does_not_search_the_web(self) -> None:
        reply = asyncio.run(
            build_fast_reply(
                "Find a puzzle under twenty dollars",
                search_fn=lambda **_: [
                    _catalog_result(title="Buffalo Games 500 Piece Jigsaw Puzzle")
                ],
            )
        )
        self.assertIn("within your $20 budget", reply.text)
        self.assertFalse(reply.live_followup_needed)

    def test_no_match_does_not_invent_a_product(self) -> None:
        reply = asyncio.run(
            build_fast_reply("Find a moon car", search_fn=lambda **_: [])
        )
        self.assertIsNone(reply.product)
        self.assertEqual(reply.citations, ())
        self.assertIn("couldn’t find a reliable 2020 catalog match", reply.text)
        self.assertEqual(reply.turn_kind, "web_fallback")
        self.assertTrue(reply.live_followup_needed)

    def test_greeting_does_not_search_the_catalog(self) -> None:
        def fail_search(**_):
            self.fail("greetings must not trigger product retrieval")

        reply = asyncio.run(
            build_fast_reply("How are you doing today?", search_fn=fail_search)
        )
        self.assertEqual(reply.turn_kind, "conversation")
        self.assertIn("doing well", reply.text)
        self.assertIsNone(reply.product)

    def test_greeting_does_not_override_a_shopping_request(self) -> None:
        calls = []

        def fake_search(**kwargs):
            calls.append(kwargs)
            return []

        request = "Hello, I need vegetables like broccoli and lettuce"
        reply = asyncio.run(build_fast_reply(request, search_fn=fake_search))

        self.assertIsNone(conversation_reply(request))
        self.assertEqual(calls[0]["query"], "vegetables broccoli lettuce")
        self.assertEqual(calls[0]["category"], "Grocery & Gourmet Food")
        self.assertEqual(reply.turn_kind, "web_fallback")
        self.assertNotIn("doing well", reply.text)

    def test_groceries_rejects_a_semantically_similar_toy(self) -> None:
        calls = []

        def fake_search(**kwargs):
            calls.append(kwargs)
            return [
                _catalog_result(
                    title="Learning Resources Realistic-Looking Baskets of Food",
                    similarity=0.8,
                )
            ]

        reply = asyncio.run(
            build_fast_reply(
                "What groceries can I buy under 20 bucks?", search_fn=fake_search
            )
        )

        self.assertEqual(calls[0]["category"], "Grocery & Gourmet Food")
        self.assertIsNone(calls[0]["brand"])
        self.assertEqual(reply.turn_kind, "web_fallback")
        self.assertIsNone(reply.product)
        self.assertIn("under $20", reply.text)

    def test_accented_pokemon_title_is_a_reliable_match(self) -> None:
        reply = asyncio.run(
            build_fast_reply(
                "Can you find a Pokemon puzzle?",
                search_fn=lambda **_: [
                    _catalog_result(title="Pokémon 500 Piece Jigsaw Puzzle")
                ],
            )
        )
        self.assertIsNotNone(reply.product)
        self.assertTrue(reply.live_followup_needed)

    def test_specific_product_automatically_checks_the_web(self) -> None:
        reply = asyncio.run(
            build_fast_reply(
                "Nerf Strongarm blaster",
                search_fn=lambda **_: [_catalog_result()],
            )
        )
        self.assertTrue(reply.live_followup_needed)
        self.assertIn("checking current listings", reply.text)


if __name__ == "__main__":
    unittest.main()
