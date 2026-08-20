"""Regression tests for conversational requirement tracking and ranking."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from contracts import ComparisonProduct, RagResult, ShoppingContext, WebResult
from graph.fast_reply import semantic_query
from graph.preferences import (
    filter_products_by_required_facets,
    has_actionable_preference,
    is_contextual_followup_candidate,
    matched_preferences,
    rank_products_by_preferences,
    resolve_preferences,
)


def _product(
    doc_id: str,
    title: str,
    *features: str,
    similarity: float = 0.7,
) -> ComparisonProduct:
    private = RagResult(
        sku=doc_id,
        title=title,
        price=49.99,
        rating=None,
        brand=None,
        ingredients=None,
        doc_id=doc_id,
        image_url="https://example.com/item.jpg",
        product_url="https://example.com/item",
        category="Clothing, Shoes & Jewelry",
        price_low=49.99,
        price_high=49.99,
        similarity=similarity,
        budget_fit="within",
        feature_evidence=list(features),
    )
    return ComparisonProduct(private=private, live=None, conflicts=[], match=None)


class _FakeStructuredLLM:
    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, _messages):
        return SimpleNamespace(
            action="refine",
            product_query="walking shoes",
            colors=["navy"],
            sizes=[],
            materials=[],
            textures=[],
            comfort=["supportive", "cushioned"],
            features=["standing all day"],
            excluded=[],
        )


class PreferenceTests(unittest.TestCase):
    def test_one_turn_negative_color_keeps_product_family_out_of_query(self) -> None:
        text = "a backpack that's not black"

        profile = asyncio.run(
            resolve_preferences(
                text,
                semantic_query(text),
                allow_llm=False,
            )
        )

        self.assertEqual(profile.product_query, "backpack")
        self.assertEqual(profile.excluded, ["black"])
        self.assertEqual(profile.resolved_query, "backpack")
        self.assertFalse(profile.is_followup)

    def test_negative_color_followups_retain_active_product_family(self) -> None:
        previous = ShoppingContext(
            product_query="backpack",
            resolved_query="backpack",
        )

        for text in ("I don't want black", "not black"):
            with self.subTest(text=text):
                profile = asyncio.run(
                    resolve_preferences(
                        text,
                        semantic_query(text),
                        previous,
                        allow_llm=False,
                    )
                )

                self.assertEqual(profile.product_query, "backpack")
                self.assertEqual(profile.excluded, ["black"])
                self.assertEqual(profile.resolved_query, "backpack")
                self.assertTrue(profile.is_followup)
                self.assertTrue(profile.preference_changed)

    def test_pronoun_color_update_and_acknowledgement_retain_context(self) -> None:
        previous = ShoppingContext(
            product_query="backpack",
            resolved_query="backpack",
        )

        pink = asyncio.run(
            resolve_preferences(
                "I want it to be pink",
                semantic_query("I want it to be pink"),
                previous,
                allow_llm=False,
            )
        )
        acknowledged = asyncio.run(
            resolve_preferences(
                "That's right",
                semantic_query("That's right"),
                previous,
                allow_llm=False,
            )
        )

        self.assertEqual(pink.product_query, "backpack")
        self.assertEqual(pink.colors, ["pink"])
        self.assertEqual(pink.resolved_query, "backpack pink")
        self.assertTrue(pink.preference_changed)
        self.assertEqual(acknowledged.product_query, "backpack")
        self.assertEqual(acknowledged.resolved_query, "backpack")
        self.assertTrue(acknowledged.is_followup)
        self.assertFalse(acknowledged.preference_changed)

    def test_explicit_contrast_can_start_a_true_new_product_request(self) -> None:
        previous = ShoppingContext(
            product_query="backpack",
            colors=["black"],
            resolved_query="backpack black",
        )
        text = "I don't want a backpack; show me a suitcase"

        profile = asyncio.run(
            resolve_preferences(
                text,
                semantic_query(text),
                previous,
                allow_llm=False,
            )
        )

        self.assertEqual(profile.product_query, "suitcase")
        self.assertEqual(profile.resolved_query, "suitcase")
        self.assertFalse(profile.is_followup)
        self.assertEqual(profile.colors, [])

    def test_short_affirmation_stays_attached_to_the_active_request(self) -> None:
        previous = ShoppingContext(
            product_query="groceries",
            resolved_query="groceries",
        )

        self.assertTrue(is_contextual_followup_candidate("Yeah", previous))
        profile = asyncio.run(
            resolve_preferences(
                "Yeah",
                semantic_query("Yeah"),
                previous,
                allow_llm=False,
            )
        )

        self.assertTrue(profile.is_followup)
        self.assertFalse(profile.preference_changed)
        self.assertEqual(profile.product_query, "groceries")
        self.assertEqual(profile.resolved_query, "groceries")

    def test_short_affirmation_avoids_a_redundant_preference_model_call(self) -> None:
        previous = ShoppingContext(
            product_query="groceries",
            resolved_query="groceries",
        )

        def fail():
            self.fail("the dialogue layer, not preference parsing, handles confirmations")

        with patch.dict(
            "os.environ",
            {
                "PREFERENCE_LLM": "1",
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "test-key",
            },
        ):
            for text in ("Yeah", "That's right"):
                with self.subTest(text=text):
                    profile = asyncio.run(
                        resolve_preferences(
                            text,
                            semantic_query(text),
                            previous,
                            previous_answer=(
                                "Would you like pantry staples or fresh food?"
                            ),
                            llm_factory=fail,
                        )
                    )

                    self.assertEqual(profile.product_query, "groceries")
                    self.assertEqual(profile.understanding_source, "rules")

    def test_budget_only_vague_request_skips_preference_model(self) -> None:
        def fail():
            self.fail("a budget-only clarification should not spend a model call")

        with patch.dict(
            "os.environ",
            {
                "PREFERENCE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
        ):
            profile = asyncio.run(
                resolve_preferences(
                    "I want something under $10",
                    semantic_query("I want something under $10"),
                    llm_factory=fail,
                )
            )

        self.assertEqual(profile.product_query, "product")
        self.assertEqual(profile.understanding_source, "rules")

    def test_vague_placeholder_is_not_treated_as_a_product_name(self) -> None:
        for text in (
            "something blue",
            "I want something blue",
            "Show me something blue",
            "I asked for something blue",
        ):
            with self.subTest(text=text):
                profile = asyncio.run(
                    resolve_preferences(
                        text,
                        semantic_query(text),
                        allow_llm=False,
                    )
                )

                self.assertEqual(profile.product_query, "product")
                self.assertEqual(profile.colors, ["blue"])
                self.assertEqual(profile.features, [])
                self.assertNotIn("something", profile.resolved_query)
                self.assertNotIn("asked", profile.resolved_query)

    def test_home_use_case_becomes_the_product_intent_not_a_feature(self) -> None:
        previous = ShoppingContext(
            product_query="product",
            resolved_query="product",
        )

        profile = asyncio.run(
            resolve_preferences(
                "I need something for home",
                semantic_query("I need something for home"),
                previous,
                allow_llm=False,
            )
        )

        self.assertEqual(profile.product_query, "home")
        self.assertEqual(profile.features, [])
        self.assertEqual(profile.resolved_query, "home")
        self.assertTrue(profile.is_followup)
        self.assertTrue(profile.preference_changed)

    def test_recipient_is_not_treated_as_a_product_feature(self) -> None:
        for text in (
            "LEGO for my kid",
            "LEGO for my kid please",
            "LEGO for a kid",
        ):
            with self.subTest(text=text):
                profile = asyncio.run(
                    resolve_preferences(
                        text,
                        semantic_query(text),
                        allow_llm=False,
                    )
                )

                self.assertEqual(profile.product_query, "LEGO")
                self.assertEqual(profile.features, [])
                self.assertEqual(profile.resolved_query, "LEGO")

    def test_plural_adults_refines_the_active_bag_as_a_hard_audience(self) -> None:
        previous = ShoppingContext(
            product_query="bag",
            resolved_query="bag",
        )

        profile = asyncio.run(
            resolve_preferences(
                "Give bag adults",
                semantic_query("Give bag adults"),
                previous,
                allow_llm=False,
            )
        )

        self.assertEqual(profile.product_query, "bag")
        self.assertEqual(profile.sizes, ["adult"])
        self.assertEqual(profile.resolved_query, "bag adult")
        self.assertTrue(profile.is_followup)
        self.assertTrue(profile.preference_changed)

    def test_adult_audience_rejects_child_bag_and_accepts_adult_synonyms(self) -> None:
        child = _product(
            "child-bag",
            "Wildkin Kids Overnighter Duffel Bag for Boys and Girls",
            similarity=0.99,
        )
        adult = _product(
            "adult-bag",
            "Unisex Canvas Work Bag for Men and Women",
            similarity=0.70,
        )
        context = ShoppingContext(
            product_query="bag",
            sizes=["adult"],
            resolved_query="bag adult",
        )

        filtered = filter_products_by_required_facets([child, adult], context)

        self.assertEqual(filtered, [adult])
        self.assertEqual(matched_preferences(adult, context), ["adult"])

    def test_extracts_specific_requirements_without_an_llm(self) -> None:
        text = "comfortable blue leather shoes in size 10 with a soft lining"
        profile = asyncio.run(
            resolve_preferences(
                text,
                semantic_query(text),
                allow_llm=False,
            )
        )

        self.assertEqual(profile.product_query, "shoes")
        self.assertEqual(profile.colors, ["blue"])
        self.assertEqual(profile.sizes, ["size 10"])
        self.assertEqual(profile.materials, ["leather"])
        self.assertIn("soft", profile.textures)
        self.assertIn("comfortable", profile.comfort)
        self.assertIn("shoes", profile.resolved_query)

    def test_followup_replaces_color_and_size_but_preserves_other_preferences(self) -> None:
        previous = ShoppingContext(
            product_query="running shoes",
            colors=["blue"],
            sizes=["size 10"],
            materials=["mesh"],
            comfort=["cushioned"],
            resolved_query="running shoes blue size 10 mesh cushioned",
        )
        text = "Actually, black in size 11 instead"
        profile = asyncio.run(
            resolve_preferences(
                text,
                semantic_query(text),
                previous,
                allow_llm=False,
            )
        )

        self.assertTrue(profile.is_followup)
        self.assertTrue(profile.preference_changed)
        self.assertEqual(profile.product_query, "running shoes")
        self.assertEqual(profile.colors, ["black"])
        self.assertEqual(profile.sizes, ["size 11"])
        self.assertEqual(profile.materials, ["mesh"])
        self.assertEqual(profile.comfort, ["cushioned"])

    def test_size_alternatives_are_one_followup_group(self) -> None:
        previous = ShoppingContext(
            product_query="mens sportswear",
            resolved_query="mens sportswear",
        )

        profile = asyncio.run(
            resolve_preferences(
                "Medium or large?",
                semantic_query("Medium or large?"),
                previous,
                allow_llm=False,
            )
        )

        self.assertTrue(profile.is_followup)
        self.assertTrue(profile.preference_changed)
        self.assertEqual(profile.product_query, "mens sportswear")
        self.assertEqual(set(profile.sizes), {"medium", "large"})

    def test_spoken_bedding_alternatives_become_a_product_family(self) -> None:
        text = (
            "Um, I would like some stuff I can use on my bed, like a quilt or "
            "a comforter set or like a pillow, anything like that."
        )

        profile = asyncio.run(
            resolve_preferences(
                text,
                semantic_query(text),
                allow_llm=False,
            )
        )

        self.assertEqual(profile.product_query, "bedding")
        self.assertEqual(profile.resolved_query, "bedding")

    def test_bare_named_model_starts_a_new_search(self) -> None:
        previous = ShoppingContext(
            product_query="mens sportswear",
            comfort=["lightweight"],
            resolved_query="mens sportswear lightweight",
        )

        self.assertFalse(is_contextual_followup_candidate("iPhone 12", previous))
        profile = asyncio.run(
            resolve_preferences(
                "iPhone 12",
                semantic_query("iPhone 12"),
                previous,
                allow_llm=False,
            )
        )

        self.assertFalse(profile.is_followup)
        self.assertEqual(profile.product_query.casefold(), "iphone 12")
        self.assertEqual(profile.comfort, [])

    def test_unlisted_product_phrase_does_not_inherit_the_old_search(self) -> None:
        previous = ShoppingContext(
            product_query="running shoes",
            sizes=["size 11"],
            resolved_query="running shoes size 11",
        )

        self.assertFalse(
            is_contextual_followup_candidate("insulated water bottle", previous)
        )
        profile = asyncio.run(
            resolve_preferences(
                "insulated water bottle",
                semantic_query("insulated water bottle"),
                previous,
                allow_llm=False,
            )
        )

        self.assertEqual(profile.product_query, "insulated water bottle")
        self.assertEqual(profile.sizes, [])

    def test_explicit_new_item_cues_clear_the_previous_product_context(self) -> None:
        previous = ShoppingContext(
            product_query="toy animals",
            colors=["blue"],
            excluded=["black"],
            resolved_query="toy animals blue",
        )

        for text in (
            "I want some vegetables",
            "Now I need vegetables",
            "Next, find vegetables",
            "I also want vegetables",
            "Also I need vegetables",
            "Also vegetables",
            "Moving on, let's look for vegetables",
        ):
            with self.subTest(text=text):
                profile = asyncio.run(
                    resolve_preferences(
                        text,
                        semantic_query(text),
                        previous,
                        allow_llm=False,
                    )
                )

                self.assertEqual(profile.product_query, "vegetables")
                self.assertEqual(profile.resolved_query, "vegetables")
                self.assertEqual(profile.colors, [])
                self.assertEqual(profile.excluded, [])
                self.assertFalse(profile.is_followup)

    def test_also_pronoun_facet_update_keeps_the_active_product(self) -> None:
        previous = ShoppingContext(
            product_query="toy animals",
            colors=["blue"],
            resolved_query="toy animals blue",
        )

        for text in ("I also want it green", "Also blue", "Also padded"):
            with self.subTest(text=text):
                profile = asyncio.run(
                    resolve_preferences(
                        text,
                        semantic_query(text),
                        previous,
                        allow_llm=False,
                    )
                )

                self.assertEqual(profile.product_query, "toy animals")
                self.assertTrue(profile.is_followup)

        phone = ShoppingContext(
            product_query="iphone",
            resolved_query="iphone",
        )
        camera = asyncio.run(
            resolve_preferences(
                "Also camera",
                semantic_query("Also camera"),
                phone,
                allow_llm=False,
            )
        )

        self.assertEqual(camera.product_query, "iphone")
        self.assertEqual(camera.features, ["camera"])
        self.assertTrue(camera.is_followup)

    def test_domain_feature_answer_remains_contextual(self) -> None:
        previous = ShoppingContext(
            product_query="iphone",
            resolved_query="iphone",
        )

        self.assertTrue(
            is_contextual_followup_candidate("a good camera", previous)
        )
        profile = asyncio.run(
            resolve_preferences(
                "a good camera",
                semantic_query("a good camera"),
                previous,
                allow_llm=False,
            )
        )

        self.assertTrue(profile.preference_changed)
        self.assertEqual(profile.product_query, "iphone")
        self.assertEqual(profile.features, ["good camera"])

    def test_broad_home_answer_becomes_a_search_direction(self) -> None:
        previous = ShoppingContext(product_query="home", resolved_query="home")

        profile = asyncio.run(
            resolve_preferences(
                "organization",
                semantic_query("organization"),
                previous,
                allow_llm=False,
            )
        )

        self.assertTrue(profile.is_followup)
        self.assertTrue(profile.preference_changed)
        self.assertEqual(profile.product_query, "organization")

    def test_shopper_can_clear_a_generic_feature_request(self) -> None:
        previous = ShoppingContext(
            product_query="iphone 12",
            features=["good camera"],
            resolved_query="iphone 12 good camera",
        )
        text = "I don't care about any feature."

        self.assertTrue(has_actionable_preference(text))
        profile = asyncio.run(
            resolve_preferences(
                text,
                semantic_query(text),
                previous,
                allow_llm=False,
            )
        )

        self.assertTrue(profile.is_followup)
        self.assertTrue(profile.preference_changed)
        self.assertEqual(profile.product_query, "iphone 12")
        self.assertEqual(profile.features, [])
        self.assertEqual(profile.resolved_query, "iphone 12")

    def test_actionable_rejection_can_search_immediately(self) -> None:
        self.assertTrue(has_actionable_preference("I don't like those; make them blue"))
        self.assertFalse(has_actionable_preference("I don't like those"))

    def test_hyphenated_named_size_does_not_create_an_empty_size(self) -> None:
        previous = ShoppingContext(
            product_query="blanket",
            sizes=["queen"],
            resolved_query="blanket queen",
        )
        text = "Actually, make it king-size and plush"

        profile = asyncio.run(
            resolve_preferences(
                text,
                semantic_query(text),
                previous,
                allow_llm=False,
            )
        )

        self.assertEqual(profile.sizes, ["king"])
        self.assertEqual(profile.textures, ["plush"])

    def test_ambiguous_need_uses_existing_llm_with_bounded_profile_output(self) -> None:
        previous = ShoppingContext(
            product_query="walking shoes",
            colors=["red"],
            resolved_query="walking shoes red",
        )
        text = "My feet ache after standing all day, and I would rather have navy"
        with patch.dict(
            "os.environ",
            {
                "PREFERENCE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ):
            profile = asyncio.run(
                resolve_preferences(
                    text,
                    semantic_query(text),
                    previous,
                    llm_factory=lambda: _FakeStructuredLLM(),
                )
            )

        self.assertEqual(profile.understanding_source, "llm")
        self.assertTrue(profile.is_followup)
        self.assertTrue(profile.preference_changed)
        self.assertEqual(profile.colors, ["navy"])
        self.assertEqual(profile.comfort, ["supportive", "cushioned"])
        self.assertIn("standing all day", profile.resolved_query)

    def test_products_are_ranked_by_grounded_preference_coverage(self) -> None:
        profile = ShoppingContext(
            product_query="walking shoes",
            colors=["blue"],
            comfort=["cushioned", "supportive"],
            resolved_query="walking shoes blue cushioned supportive",
        )
        partial = _product(
            "PARTIAL",
            "Blue Walking Shoes",
            "Light everyday upper",
            similarity=0.95,
        )
        strong = _product(
            "STRONG",
            "Blue Walking Shoes",
            "Cushioned footbed with supportive arch construction",
            similarity=0.6,
        )

        ranked = rank_products_by_preferences([partial, strong], profile)

        self.assertEqual(ranked[0].private.doc_id, "STRONG")
        self.assertEqual(
            matched_preferences(ranked[0], profile),
            ["blue", "cushioned", "supportive"],
        )

    def test_required_color_filters_unconfirmed_cards_from_the_grid(self) -> None:
        profile = ShoppingContext(
            product_query="storage",
            colors=["blue"],
            resolved_query="storage blue",
        )
        blue = _product("BLUE", "Blue Storage Bin", "Blue fabric exterior")
        unconfirmed = _product("PLAIN", "Home Storage Bin", "Foldable fabric bin")

        filtered = filter_products_by_required_facets(
            [unconfirmed, blue],
            profile,
        )

        self.assertEqual([item.private.doc_id for item in filtered], ["BLUE"])

    def test_excluded_color_filters_private_and_live_grounded_evidence(self) -> None:
        profile = ShoppingContext(
            product_query="backpack",
            excluded=["black"],
            resolved_query="backpack",
        )
        black_private = _product(
            "BLACK-PRIVATE",
            "Everest Deluxe Small Backpack, Black, One Size",
        )
        black_live = ComparisonProduct(
            private=None,
            live=WebResult(
                title="Black Travel Backpack",
                url="https://example.com/black-backpack",
                snippet="A compact black backpack for travel.",
            ),
            conflicts=[],
            match=None,
        )
        pink_private = _product(
            "PINK-PRIVATE",
            "Pink Canvas Travel Backpack",
        )

        filtered = filter_products_by_required_facets(
            [black_private, black_live, pink_private],
            profile,
        )

        self.assertEqual(filtered, [pink_private])


if __name__ == "__main__":
    unittest.main()
