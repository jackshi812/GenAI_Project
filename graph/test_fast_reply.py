"""Regression tests for the sub-three-second grounded first-response path."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from graph.decision import ShoppingDirection
from graph.fast_reply import (
    build_fast_reply,
    conversation_reply,
    contextualize_followup,
    explicitly_requests_live,
    extract_brand,
    extract_budget_bounds,
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
    def test_social_preamble_and_source_words_never_become_product_terms(self) -> None:
        text = "How's it going? I need a travel bag from the web"

        self.assertEqual(semantic_query(text), "travel bag")
        self.assertTrue(explicitly_requests_live(text))

    def test_extracts_numeric_and_spoken_budgets(self) -> None:
        self.assertEqual(extract_budget_max("Find a puzzle under $20"), 20.0)
        self.assertEqual(
            extract_budget_max("Find a puzzle under twenty dollars"), 20.0
        )
        self.assertEqual(
            extract_budget_max("Find a toy below one thousand dollars"), 1_000.0
        )

    def test_extracts_numeric_and_spoken_budget_ranges(self) -> None:
        self.assertEqual(
            extract_budget_bounds("Find a LEGO toy between 50 and 100 dollars"),
            (50.0, 100.0),
        )
        self.assertEqual(
            extract_budget_bounds(
                "Find a LEGO toy between fifty and one hundred dollars"
            ),
            (50.0, 100.0),
        )
        self.assertEqual(
            extract_budget_bounds("lego toy between 50 100"),
            (50.0, 100.0),
        )
        self.assertEqual(
            extract_budget_bounds("lego toy from $50 to $100"),
            (50.0, 100.0),
        )
        self.assertEqual(
            extract_budget_bounds("lego toy $50-$100"),
            (50.0, 100.0),
        )

    def test_budget_range_is_removed_from_query_and_sent_as_metadata(self) -> None:
        calls = []

        def fake_search(**kwargs):
            calls.append(kwargs)
            return [
                _catalog_result(
                    title="LEGO City Space Explorer Toy Set",
                    category="Toys & Games",
                )
            ]

        asyncio.run(
            build_fast_reply(
                "lego toy between 50 100",
                search_fn=fake_search,
            )
        )

        self.assertEqual(calls[0]["query"], "lego toy")
        self.assertEqual(calls[0]["price_min"], 50.0)
        self.assertEqual(calls[0]["price_max"], 100.0)

    def test_followup_keeps_or_overrides_the_pending_budget(self) -> None:
        self.assertEqual(
            contextualize_followup("a toy", 20.0),
            "a toy under $20",
        )
        self.assertEqual(
            contextualize_followup("a toy under $50", 20.0),
            "a toy under $50",
        )
        self.assertEqual(contextualize_followup("thanks", 20.0), "thanks")
        self.assertEqual(
            contextualize_followup("I don't like them", 20.0),
            "I don't like them under $20",
        )
        self.assertEqual(
            contextualize_followup("show me blue ones", 100.0, 50.0),
            "show me blue ones between $50 and $100",
        )

    def test_semantic_query_removes_budget_and_routing_words(self) -> None:
        self.assertEqual(
            semantic_query("Please find me a current Nerf blaster under $20"),
            "Nerf blaster",
        )
        self.assertEqual(
            semantic_query("I asked for something blue"),
            "something blue",
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
        self.assertLessEqual(len(reply.text.split()), 30)
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
        self.assertFalse(reply.text.startswith("Oh"))
        self.assertIn("500-piece jigsaw puzzle", reply.text)
        self.assertIn("fits your $20 budget", reply.text)
        self.assertFalse(reply.live_followup_needed)

    def test_vague_budget_request_asks_a_followup_without_searching(self) -> None:
        def fail_search(**_):
            self.fail("a vague request must be clarified before retrieval")

        reply = asyncio.run(
            build_fast_reply(
                "What is something I can buy under 20 bucks?",
                search_fn=fail_search,
            )
        )

        self.assertEqual(reply.turn_kind, "clarification")
        self.assertFalse(reply.live_followup_needed)
        self.assertIsNone(reply.product)
        self.assertIn("what would you like", reply.text.casefold())
        self.assertNotIn("toy, game", reply.text.casefold())
        self.assertIn("$20", reply.text)
        self.assertLessEqual(len(reply.text.split()), 30)

    def test_vague_color_request_lets_agent_choose_without_literal_search(self) -> None:
        calls = []

        def fake_search(**kwargs):
            calls.append(kwargs)
            result = _catalog_result(
                title="Blue Home Storage Bin",
                category="Home & Kitchen",
            )
            result["feature_evidence"] = ["Blue fabric storage bin"]
            return [result]

        direction = ShoppingDirection(
            option_id="home_storage",
            query="storage",
            category="Home & Kitchen",
            label="a useful home-storage item",
            selected_by="llm",
        )
        with patch(
            "graph.fast_reply.choose_direction",
            new=AsyncMock(return_value=direction),
        ):
            reply = asyncio.run(
                build_fast_reply(
                    "I asked for something blue",
                    search_fn=fake_search,
                )
            )

        self.assertEqual(calls[0]["query"], "storage")
        self.assertNotIn("something", calls[0]["query"])
        self.assertEqual(calls[0]["category"], "Home & Kitchen")
        self.assertEqual(reply.shopping_context.product_query, "storage")
        self.assertEqual(reply.shopping_context.colors, ["blue"])
        self.assertEqual(reply.resolved_transcript, "Find storage blue")
        self.assertIsNotNone(reply.product)
        self.assertTrue(reply.text.startswith("I’d go with"))

    def test_home_followup_narrows_the_need_instead_of_repeating_or_searching(self) -> None:
        def fail_search(**_):
            self.fail("a category-level home request still needs one focused question")

        with patch.dict("os.environ", {"DIALOGUE_LLM": "0"}):
            reply = asyncio.run(
                build_fast_reply(
                    "I need something for home",
                    search_fn=fail_search,
                    dialogue_context={
                        "budget_max": 10.0,
                        "shopping_context": {
                            "product_query": "product",
                            "resolved_query": "product",
                        },
                    },
                )
            )

        self.assertEqual(reply.turn_kind, "clarification")
        self.assertIn("for your home", reply.text.casefold())
        self.assertIn("what problem", reply.text.casefold())
        self.assertIn("$10", reply.text)
        self.assertNotIn("what kind of product", reply.text.casefold())

    def test_weak_attribute_coverage_is_not_presented_as_a_strong_match(self) -> None:
        weak = _catalog_result(
            title="Pink Slipper Shoes for Toddlers",
            similarity=0.8,
        )
        weak["feature_evidence"] = ["One size fits most children under 10 years old"]

        reply = asyncio.run(
            build_fast_reply(
                "Find comfortable blue shoes in size 10",
                search_fn=lambda **_: [weak],
            )
        )

        self.assertEqual(reply.turn_kind, "web_fallback")
        self.assertIsNone(reply.product)
        self.assertTrue(reply.live_followup_needed)
        self.assertIn("doesn’t confirm enough", reply.text)

    def test_rejecting_results_asks_for_a_preference_without_searching(self) -> None:
        def fail_search(**_):
            self.fail("feedback about prior results must not become a product search")

        reply = asyncio.run(
            build_fast_reply(
                "I don't like them under $20",
                search_fn=fail_search,
                dialogue_context={
                    "budget_max": 20.0,
                    "shopping_context": {
                        "product_query": "puzzle",
                        "resolved_query": "puzzle",
                    },
                },
            )
        )

        self.assertEqual(reply.turn_kind, "refinement")
        self.assertFalse(reply.live_followup_needed)
        self.assertIsNone(reply.product)
        self.assertIn("What should I adjust", reply.text)
        self.assertIn("$20 limit", reply.text)

    def test_incomplete_preference_change_asks_for_the_missing_value(self) -> None:
        def fail_search(**_):
            self.fail("an incomplete preference change must be clarified")

        reply = asyncio.run(
            build_fast_reply(
                "Change the color",
                search_fn=fail_search,
                dialogue_context={
                    "budget_max": 50.0,
                    "shopping_context": {
                        "product_query": "running shoes",
                        "colors": ["blue"],
                        "resolved_query": "running shoes blue",
                    },
                },
            )
        )

        self.assertEqual(reply.turn_kind, "clarification")
        self.assertIn("what color", reply.text.casefold())
        self.assertIn("$50 limit", reply.text)

    def test_delegated_choice_resolves_to_a_grounded_catalog_search(self) -> None:
        calls = []

        def fake_search(**kwargs):
            calls.append(kwargs)
            return [
                _catalog_result(
                    title="Cosco Blossom Home Storage Bin",
                    category="Home & Kitchen",
                )
            ]

        direction = ShoppingDirection(
            option_id="home_storage",
            query="storage",
            category="Home & Kitchen",
            label="a useful home-storage item",
            selected_by="llm",
        )
        with patch(
            "graph.fast_reply.choose_direction",
            new=AsyncMock(return_value=direction),
        ):
            reply = asyncio.run(
                build_fast_reply(
                    "I don't know, help me decide under $20",
                    search_fn=fake_search,
                    dialogue_context={"budget_max": 20.0},
                )
            )

        self.assertEqual(calls[0]["query"], "storage")
        self.assertEqual(calls[0]["category"], "Home & Kitchen")
        self.assertEqual(calls[0]["price_max"], 20.0)
        self.assertEqual(calls[0]["k"], 12)
        self.assertIsNotNone(reply.product)
        self.assertEqual(reply.resolved_transcript, "Find storage under $20")
        self.assertEqual(reply.decision_source, "llm")
        self.assertTrue(reply.text.startswith("I’d go with"))

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

    def test_explicit_new_item_cues_clear_context_before_fast_search(self) -> None:
        previous = {
            "product_query": "toy animals",
            "colors": ["blue"],
            "excluded": ["black"],
            "resolved_query": "toy animals blue",
        }

        for text in (
            "Next, find vegetables",
            "I also want vegetables",
            "Also vegetables",
        ):
            calls = []

            def fake_search(**kwargs):
                calls.append(kwargs)
                return [
                    _catalog_result(
                        title="Fresh Vegetable Basket",
                        category="Grocery & Gourmet Food",
                    )
                ]

            with self.subTest(text=text):
                reply = asyncio.run(
                    build_fast_reply(
                        text,
                        search_fn=fake_search,
                        dialogue_context={
                            "shopping_context": previous,
                            "budget_max": 20.0,
                        },
                    )
                )

                self.assertEqual(calls[0]["query"], "vegetables")
                self.assertIsNone(calls[0]["price_max"])
                self.assertEqual(reply.shopping_context.product_query, "vegetables")
                self.assertEqual(reply.shopping_context.colors, [])
                self.assertEqual(reply.shopping_context.excluded, [])
                self.assertFalse(reply.shopping_context.is_followup)

    def test_completed_cart_acknowledgement_does_not_search(self) -> None:
        def fail_search(**_):
            self.fail("a completed-cart acknowledgement must not trigger retrieval")

        self.assertIsNone(conversation_reply("Add it to cart"))
        previous = {
            "product_query": "vegetables",
            "resolved_query": "vegetables",
        }
        reply = asyncio.run(
            build_fast_reply(
                "Okay, I added it to my cart",
                search_fn=fail_search,
                dialogue_context={"shopping_context": previous},
            )
        )

        self.assertEqual(reply.turn_kind, "conversation")
        self.assertEqual(reply.shopping_context.product_query, "vegetables")
        self.assertIn("shop for next", reply.text.casefold())

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
