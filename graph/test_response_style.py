"""Tests for warm, grounded shopping language."""

from __future__ import annotations

import unittest

from contracts import ComparisonProduct, RagResult, ShoppingContext, WebResult
from graph.response_style import (
    catalog_recommendation,
    clarification_reply,
    grounded_comparison,
    is_delegated_choice,
    is_rejection_followup,
    is_vague_shopping_query,
    refinement_reply,
    web_recommendation,
)


def _puzzle() -> RagResult:
    return RagResult(
        sku="puzzle",
        title="Buffalo Games - Pokémon Bubble - 500 Piece Jigsaw Puzzle",
        price=10.99,
        rating=None,
        brand="Buffalo",
        ingredients=None,
        doc_id="CAT-PUZZLE",
        image_url="https://example.com/puzzle.jpg",
        product_url="https://example.com/puzzle",
        category="Toys & Games",
        price_low=10.99,
        price_high=10.99,
        similarity=0.9,
        budget_fit="within",
    )


class ResponseStyleTests(unittest.TestCase):
    def test_obviously_generic_queries_need_clarification(self) -> None:
        self.assertTrue(is_vague_shopping_query("something"))
        self.assertTrue(is_vague_shopping_query("product"))
        self.assertTrue(is_vague_shopping_query("something cool"))
        self.assertTrue(is_vague_shopping_query("home"))
        self.assertFalse(is_vague_shopping_query("500 piece puzzle"))
        self.assertFalse(is_vague_shopping_query("kitchen item"))

    def test_clarification_is_warm_specific_and_brief(self) -> None:
        text = clarification_reply(20.0)

        self.assertIn("$20", text)
        self.assertIn("what would you like", text.casefold())
        self.assertIn("?", text)
        self.assertNotIn("toy, game", text.casefold())
        self.assertLessEqual(len(text.split()), 30)

    def test_home_clarification_advances_the_conversation(self) -> None:
        text = clarification_reply(10.0, transcript="I need something for home")

        self.assertIn("for your home", text.casefold())
        self.assertIn("what problem", text.casefold())
        self.assertIn("$10", text)
        self.assertNotIn("what kind of product", text.casefold())
        self.assertLessEqual(len(text.split()), 30)

    def test_catalog_recommendation_mentions_grounded_feature_and_fit(self) -> None:
        text = catalog_recommendation(
            _puzzle(),
            query="500 piece puzzle",
            budget_max=20.0,
            checking_live=False,
        )

        self.assertFalse(text.startswith("Oh"))
        self.assertIn("500-piece jigsaw puzzle", text)
        self.assertIn("$10.99", text)
        self.assertIn("fits your $20 budget", text)
        self.assertLessEqual(len(text.split()), 30)

    def test_web_recommendation_preserves_recorded_provenance(self) -> None:
        product = WebResult(
            title="LEGO Classic Creative Suitcase 213 Pieces",
            url="https://example.com/lego",
            snippet="Recorded result",
            price=12.95,
            availability=None,
            image_url=None,
            rating=None,
            origin="recorded_fixture",
        )

        text = web_recommendation(
            product,
            query="LEGO suitcase",
            budget_max=20.0,
            numeric_price=12.95,
        )

        self.assertFalse(text.startswith("Oh"))
        self.assertIn("213 pieces", text)
        self.assertIn("recorded web price", text)
        self.assertIn("fits your $20 budget", text)
        self.assertNotIn("current web price", text)
        self.assertLessEqual(len(text.split()), 30)

    def test_rejection_is_dialogue_feedback_not_a_product_query(self) -> None:
        self.assertTrue(is_rejection_followup("I don't like them"))
        self.assertTrue(is_rejection_followup("I don't like it"))
        self.assertTrue(is_rejection_followup("None of these work for me"))
        self.assertTrue(is_rejection_followup("Show me something different"))
        self.assertFalse(is_rejection_followup("Find dolls I like"))

        text = refinement_reply(20.0)
        self.assertIn("what would you like instead", text.casefold())
        self.assertIn("$20 limit", text)
        self.assertLessEqual(len(text.split()), 30)

    def test_shopper_can_delegate_the_choice(self) -> None:
        self.assertTrue(is_delegated_choice("I don't know, help me decide"))
        self.assertTrue(is_delegated_choice("You pick for me"))
        self.assertTrue(is_delegated_choice("Surprise me"))
        self.assertTrue(is_delegated_choice("Can you just give me give me anything?"))
        self.assertFalse(is_delegated_choice("Find me a puzzle"))

        text = catalog_recommendation(
            _puzzle(),
            query="puzzle",
            budget_max=20.0,
            checking_live=False,
            decisive=True,
        )
        self.assertTrue(text.startswith("I’d go with"))
        self.assertIn("$10.99", text)
        self.assertLessEqual(len(text.split()), 30)

    def test_grounded_recommendations_do_not_share_a_canned_opener(self) -> None:
        first = catalog_recommendation(
            _puzzle(),
            query="500 piece puzzle",
            budget_max=20.0,
            checking_live=False,
        )
        second_product = _puzzle().model_copy(
            update={
                "doc_id": "CAT-BLASTER",
                "title": (
                    "Nerf N Strike Elite Strongarm Toy Blaster with Rotating "
                    "Barrel and Slam Fire"
                ),
                "price": 13.99,
                "price_low": 13.99,
                "price_high": 13.99,
            }
        )
        second = catalog_recommendation(
            second_product,
            query="Nerf blaster",
            budget_max=20.0,
            checking_live=False,
        )

        self.assertNotEqual(first.split(".", 1)[0], second.split(".", 1)[0])
        self.assertNotIn("Oh, I found", first + second)

    def test_comparison_explains_supported_fit_and_missing_confirmation(self) -> None:
        strong = _puzzle().model_copy(
            update={
                "title": "Blue Soft Travel Pillow",
                "feature_evidence": ["Cushioned supportive fill"],
            }
        )
        partial = _puzzle().model_copy(
            update={
                "doc_id": "CAT-PILLOW-2",
                "title": "Blue Travel Pillow",
                "feature_evidence": [],
            }
        )
        profile = ShoppingContext(
            product_query="travel pillow",
            colors=["blue"],
            textures=["soft"],
            comfort=["cushioned", "supportive"],
            resolved_query="travel pillow blue soft cushioned supportive",
        )
        products = [
            ComparisonProduct(private=strong, live=None, conflicts=[], match=None),
            ComparisonProduct(private=partial, live=None, conflicts=[], match=None),
        ]

        text = grounded_comparison(products, profile)

        self.assertIn("Blue Soft Travel Pillow", text)
        self.assertIn("Blue Travel Pillow", text)
        self.assertIn("confirms blue", text)
        self.assertTrue("closer fit" in text or "covers more" in text)
        self.assertLessEqual(len(text.split()), 30)


if __name__ == "__main__":
    unittest.main()
