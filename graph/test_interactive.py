"""Checks for the low-latency LangGraph execution mode."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from contracts import Citation, ComparisonProduct, RagResult, ShoppingContext, WebResult
from graph.answer import AnswerOutput
from graph.build import _run, build_graph
from graph.decision import ShoppingDirection


def _catalog_product() -> RagResult:
    return RagResult(
        sku="pantry-box",
        title="Fresh Grocery Pantry Box",
        price=18.0,
        rating=None,
        brand="Fresh",
        ingredients=None,
        doc_id="CAT-PANTRY",
        image_url="https://example.com/pantry.jpg",
        product_url="https://example.com/pantry",
        category="Grocery & Gourmet Food",
        price_low=18.0,
        price_high=18.0,
        similarity=0.9,
        budget_fit="within",
    )


def _live_product() -> WebResult:
    return WebResult(
        title="Pokemon Trading Card Booster Pack",
        url="https://www.walmart.com/ip/pokemon-booster",
        snippet="Walmart",
        price=14.99,
        availability="Delivery",
        image_url="https://example.com/pokemon.jpg",
        rating=4.7,
        origin="live_serper",
    )


class _Tools:
    def __init__(self, rag_results: list[RagResult] | None = None) -> None:
        self.rag_results = rag_results or []
        self.rag_calls = []
        self.web_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def rag_search(self, query: str, **filters):
        self.rag_calls.append((query, filters))
        return self.rag_results

    async def web_search(self, query: str, num: int = 10):
        self.web_calls.append((query, num))
        return [_live_product()]


class InteractiveGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_twelve_ranked_candidates_return_first_six_with_one_live_lookup(self) -> None:
        candidates = [
            _catalog_product().model_copy(
                update={
                    "sku": f"pantry-box-{index}",
                    "doc_id": f"CAT-PANTRY-{index}",
                    "title": f"Fresh Grocery Pantry Box {index}",
                    "similarity": 0.99 - (index / 100),
                }
            )
            for index in range(12)
        ]
        tools = _Tools(candidates)

        result = await _run(
            "Find current groceries under $20",
            tools,
            graph_mode="interactive",
            dialogue_context={"force_live": True},
        )

        self.assertEqual(tools.rag_calls[0][1]["k"], 12)
        self.assertEqual(len(tools.web_calls), 1)
        self.assertEqual(
            [product.private.doc_id for product in result.products],
            [f"CAT-PANTRY-{index}" for index in range(6)],
        )
        self.assertEqual(result.products[0].private.doc_id, "CAT-PANTRY-0")
        self.assertEqual(
            result.top_recommendation.product_key,
            "catalog:CAT-PANTRY-0",
        )

    async def test_internal_live_routing_does_not_pollute_the_shopper_query(self) -> None:
        tools = _Tools([_catalog_product()])

        await _run(
            "Find me groceries under $20",
            tools,
            graph_mode="interactive",
            dialogue_context={"force_live": True},
        )

        self.assertEqual(tools.rag_calls[0][0], "groceries")
        self.assertNotIn("web", tools.rag_calls[0][0].casefold())
        self.assertEqual(len(tools.web_calls), 1)

    async def test_named_product_uses_one_web_call_and_no_llm_wait(self) -> None:
        tools = _Tools()

        result = await _run(
            "Find me Pokemon cards under $25",
            tools,
            graph_mode="interactive",
        )

        self.assertEqual(len(tools.rag_calls), 1)
        self.assertEqual(len(tools.web_calls), 1)
        self.assertEqual(result.products[0].live.title, _live_product().title)
        self.assertIn(_live_product().url, [item.url for item in result.citations])
        self.assertEqual(
            [step.node for step in result.steps if step.node in {"router", "planner", "answerer"}],
            ["router", "planner", "answerer"],
        )
        self.assertIn("evidence-only", result.steps[-1].detail)

    async def test_broad_catalog_request_skips_web_when_rag_matches(self) -> None:
        tools = _Tools([_catalog_product()])

        result = await _run(
            "What groceries can I buy under $20?",
            tools,
            graph_mode="interactive",
        )

        self.assertEqual(len(tools.web_calls), 0)
        self.assertEqual(result.products[0].private.doc_id, "CAT-PANTRY")
        self.assertEqual(
            tools.rag_calls[0][1]["category"], "Grocery & Gourmet Food"
        )
        self.assertEqual(tools.rag_calls[0][1]["price_max"], 20.0)
        self.assertFalse(result.answer_text.startswith("Oh"))
        self.assertNotIn("matches your", result.answer_text.casefold())
        self.assertNotIn("groceries request", result.answer_text.casefold())
        self.assertIn("fits your $20 budget", result.answer_text)

    async def test_budget_range_and_top_recommendation_share_one_canonical_product(self) -> None:
        top = _catalog_product().model_copy(
            update={
                "sku": "lego-top",
                "doc_id": "CAT-LEGO-TOP",
                "title": "LEGO City Space Explorer Toy Set",
                "category": "Toys & Games",
                "price": 75.0,
                "price_low": 75.0,
                "price_high": 75.0,
                "similarity": 0.95,
            }
        )
        later = top.model_copy(
            update={
                "sku": "lego-later",
                "doc_id": "CAT-LEGO-LATER",
                "title": "WANGE Taipei 101 LEGO Compatible Toy Set",
                "price": 80.0,
                "price_low": 80.0,
                "price_high": 80.0,
                "similarity": 0.8,
            }
        )
        tools = _Tools([top, later])
        later_draft = AnswerOutput(
            answer_text=(
                "Top recommendation: WANGE Taipei 101 LEGO Compatible Toy Set. "
                "It matches your LEGO toy request."
            ),
            cited_doc_ids=["CAT-LEGO-LATER"],
            cited_urls=[],
        )

        with patch.dict(
            "os.environ",
            {
                "NATURAL_RESPONSE_LLM": "1",
                "LLM_PROVIDER": "anthropic",
                "ANTHROPIC_API_KEY": "test-key",
            },
            clear=False,
        ), patch(
            "graph.answer._answer_call",
            new=AsyncMock(return_value=later_draft),
        ):
            result = await _run(
                "lego toy between 50 100",
                tools,
                graph_mode="interactive",
            )

        query, filters = tools.rag_calls[0]
        self.assertEqual(query, "lego toy")
        self.assertEqual(filters["price_min"], 50.0)
        self.assertEqual(filters["price_max"], 100.0)
        self.assertEqual(result.products[0].private.doc_id, "CAT-LEGO-TOP")
        self.assertEqual(
            result.top_recommendation.product_key,
            "catalog:CAT-LEGO-TOP",
        )
        self.assertIn("LEGO City Space Explorer Toy", result.answer_text)
        self.assertIn(result.top_recommendation.reason, result.answer_text)
        self.assertNotIn("WANGE Taipei 101", result.answer_text)
        self.assertFalse(result.answer_text.startswith("Top recommendation:"))
        self.assertLessEqual(len(result.answer_text.split()), 30)

    async def test_vague_budget_request_asks_followup_without_tools(self) -> None:
        tools = _Tools([_catalog_product()])

        result = await _run(
            "I want something under 20 bucks",
            tools,
            graph_mode="interactive",
        )

        self.assertEqual(tools.rag_calls, [])
        self.assertEqual(tools.web_calls, [])
        self.assertEqual(result.products, [])
        self.assertIn("Clarifying question", result.plan)
        self.assertIn("what would you like", result.answer_text.casefold())
        self.assertNotIn("toy, game", result.answer_text.casefold())
        self.assertIn("$20", result.answer_text)

    async def test_vague_color_request_uses_agent_direction_not_literal_phrase(self) -> None:
        catalog_products = [
            _catalog_product().model_copy(
                update={
                    "sku": f"blue-storage-{index}",
                    "doc_id": f"CAT-BLUE-STORAGE-{index}",
                    "title": f"Blue Home Storage Bin {index}",
                    "category": "Home & Kitchen",
                    "feature_evidence": ["Blue fabric storage bin"],
                }
            )
            for index in range(6)
        ]
        tools = _Tools(catalog_products)
        direction = ShoppingDirection(
            option_id="home_storage",
            query="storage",
            category="Home & Kitchen",
            label="a useful home-storage item",
            selected_by="llm",
        )

        with patch(
            "graph.interactive.choose_direction",
            new=AsyncMock(return_value=direction),
        ):
            result = await _run(
                "something blue",
                tools,
                graph_mode="interactive",
            )

        self.assertEqual(tools.rag_calls[0][0], "storage")
        self.assertNotIn("something", tools.rag_calls[0][0])
        self.assertEqual(tools.rag_calls[0][1]["category"], "Home & Kitchen")
        self.assertEqual(result.shopping_context.product_query, "storage")
        self.assertEqual(result.shopping_context.colors, ["blue"])
        self.assertEqual(len(result.products), 6)

    async def test_home_answer_gets_a_more_specific_followup_without_repeating(self) -> None:
        tools = _Tools([_catalog_product()])
        prior = ShoppingContext(
            product_query="product",
            resolved_query="product",
        )

        with patch.dict("os.environ", {"DIALOGUE_LLM": "0"}):
            result = await _run(
                "I need something for home",
                tools,
                graph_mode="interactive",
                dialogue_context={
                    "budget_max": 10.0,
                    "shopping_context": prior,
                },
            )

        self.assertEqual(tools.rag_calls, [])
        self.assertEqual(tools.web_calls, [])
        self.assertEqual(result.shopping_context.product_query, "home")
        self.assertNotIn("What kind of product", result.answer_text)
        self.assertIn("for your home", result.answer_text.casefold())
        self.assertIn("what problem", result.answer_text.casefold())
        self.assertIn("$10", result.answer_text)
        self.assertEqual(result.products, [])

    async def test_conversation_skips_product_tools(self) -> None:
        tools = _Tools()

        result = await _run(
            "How are you doing today?",
            tools,
            graph_mode="interactive",
        )

        self.assertEqual(tools.rag_calls, [])
        self.assertEqual(tools.web_calls, [])
        self.assertIn("thanks for asking", result.answer_text)

    async def test_navigation_and_termination_skip_all_product_tools(self) -> None:
        previous = ShoppingContext(product_query="bag", resolved_query="bag")
        for text in ("Oh no go back", "search result", "Okay that's all"):
            with self.subTest(text=text):
                tools = _Tools([_catalog_product()])
                result = await _run(
                    text,
                    tools,
                    graph_mode="interactive",
                    dialogue_context={"shopping_context": previous},
                )

                self.assertEqual(tools.rag_calls, [])
                self.assertEqual(tools.web_calls, [])
                self.assertEqual(result.products, [])
                self.assertLessEqual(len(result.answer_text.split()), 30)

    async def test_plural_adult_bag_prefers_grounded_adult_web_evidence(self) -> None:
        wildkin = _catalog_product().model_copy(
            update={
                "sku": "wildkin-kids-bag",
                "doc_id": "CAT-WILDKIN-KIDS",
                "title": "Wildkin Kids Overnighter Duffel Bag for Boys and Girls",
                "category": "Clothing, Shoes & Jewelry",
                "similarity": 0.99,
            }
        )
        adult_bag = WebResult(
            title="Unisex Canvas Work Bag for Men and Women",
            url="https://www.walmart.com/ip/adult-canvas-work-bag",
            snippet="Adult unisex canvas carry bag for work and travel",
            price=24.99,
            availability="Delivery",
            image_url="https://example.com/adult-bag.jpg",
            rating=4.5,
            origin="live_serper",
        )

        class _AdultBagTools(_Tools):
            async def web_search(self, query: str, num: int = 10):
                self.web_calls.append((query, num))
                return [adult_bag]

        tools = _AdultBagTools([wildkin])
        with patch(
            "graph.interactive.natural_answer_once",
            new=AsyncMock(return_value=None),
        ):
            result = await _run(
                "Give bag adults",
                tools,
                graph_mode="interactive",
                dialogue_context={
                    "shopping_context": ShoppingContext(
                        product_query="bag",
                        resolved_query="bag",
                    )
                },
            )

        self.assertEqual(tools.rag_calls[0][0], "bag")
        self.assertEqual(tools.web_calls, [("bag adult", 12)])
        self.assertEqual(result.products[0].live.url, adult_bag.url)
        self.assertTrue(all(
            product.private is None or "kids" not in product.private.title.casefold()
            for product in result.products
        ))
        self.assertIn("adult", result.top_recommendation.reason.casefold())
        self.assertNotIn("Give bag adults", result.answer_text)
        self.assertNotIn("matches your", result.answer_text.casefold())
        self.assertLessEqual(len(result.answer_text.split()), 30)

    async def test_rejection_retains_results_and_waits_for_a_preference(self) -> None:
        tools = _Tools([_catalog_product()])
        previous = ComparisonProduct(
            private=_catalog_product(),
            live=None,
            conflicts=[],
            match=None,
        )
        citation = Citation(kind="private", label="CAT-PANTRY", url=None)

        result = await _run(
            "I don't like them",
            tools,
            graph_mode="interactive",
            dialogue_context={
                "budget_max": 20.0,
                "products": [previous],
                "citations": [citation],
                "shopping_context": ShoppingContext(
                    product_query="groceries",
                    resolved_query="groceries",
                ),
            },
        )

        self.assertEqual(tools.rag_calls, [])
        self.assertEqual(tools.web_calls, [])
        self.assertIn("Preference refinement", result.plan)
        self.assertIn("what would you like instead", result.answer_text.casefold())
        self.assertIn("$20 limit", result.answer_text)
        self.assertEqual(result.products, [previous])
        self.assertEqual(result.citations, [citation])

    async def test_bare_rejection_cannot_be_overridden_by_preference_model(self) -> None:
        tools = _Tools([_catalog_product()])
        previous = ShoppingContext(
            product_query="puzzle",
            resolved_query="puzzle",
        )
        spurious_model_change = ShoppingContext(
            product_query="puzzle",
            features=["different"],
            resolved_query="puzzle different",
            is_followup=True,
            preference_changed=True,
            understanding_source="llm",
        )
        preference_parser = AsyncMock(return_value=spurious_model_change)

        with patch(
            "graph.interactive.resolve_preferences",
            new=preference_parser,
        ):
            result = await _run(
                "I don't like it",
                tools,
                graph_mode="interactive",
                dialogue_context={"shopping_context": previous},
            )

        preference_parser.assert_not_awaited()
        self.assertEqual(tools.rag_calls, [])
        self.assertEqual(tools.web_calls, [])
        self.assertIn("what would you like instead", result.answer_text.casefold())

    async def test_delegated_choice_uses_llm_direction_and_returns_six(self) -> None:
        catalog_products = [
            _catalog_product().model_copy(
                update={
                    "sku": f"storage-{index}",
                    "doc_id": f"CAT-STORAGE-{index}",
                    "title": f"Home Storage Bin {index}",
                    "category": "Home & Kitchen",
                }
            )
            for index in range(6)
        ]
        tools = _Tools(catalog_products)
        direction = ShoppingDirection(
            option_id="home_storage",
            query="storage",
            category="Home & Kitchen",
            label="a useful home-storage item",
            selected_by="llm",
        )

        with patch(
            "graph.interactive.choose_direction",
            new=AsyncMock(return_value=direction),
        ):
            result = await _run(
                "I don't know, help me decide",
                tools,
                graph_mode="interactive",
                dialogue_context={
                    "budget_max": 20.0,
                    "rejected_previous": True,
                    "avoid_categories": ["Toys & Games"],
                },
            )

        self.assertEqual(tools.rag_calls[0][0], "storage")
        self.assertEqual(tools.rag_calls[0][1]["category"], "Home & Kitchen")
        self.assertEqual(tools.rag_calls[0][1]["price_max"], 20.0)
        self.assertEqual(tools.rag_calls[0][1]["k"], 12)
        self.assertEqual(tools.web_calls, [])
        self.assertEqual(len(result.products), 6)
        self.assertIn("Agent-selected direction (llm)", result.plan)

    async def test_delegated_choice_can_pick_a_prior_grounded_result(self) -> None:
        tools = _Tools()
        first = ComparisonProduct(
            private=_catalog_product(),
            live=None,
            conflicts=[],
            match=None,
        )
        second_private = _catalog_product().model_copy(
            update={
                "sku": "second",
                "doc_id": "CAT-SECOND",
                "title": "Fresh Home Storage Set",
                "category": "Home & Kitchen",
            }
        )
        second = ComparisonProduct(
            private=second_private,
            live=None,
            conflicts=[],
            match=None,
        )

        with patch(
            "graph.interactive.choose_product_index",
            new=AsyncMock(return_value=(1, "llm")),
        ):
            result = await _run(
                "Help me decide",
                tools,
                graph_mode="interactive",
                dialogue_context={
                    "budget_max": 20.0,
                    "products": [first, second],
                    "rejected_previous": False,
                },
            )

        self.assertEqual(tools.rag_calls, [])
        self.assertEqual(tools.web_calls, [])
        self.assertEqual(result.products, [second, first])
        self.assertIn("Fresh Home Storage Set", result.answer_text)
        self.assertEqual(result.citations[0].label, "CAT-SECOND")
        self.assertEqual(
            result.top_recommendation.product_key,
            "catalog:CAT-SECOND",
        )

    async def test_preference_followup_researches_reranks_and_compares(self) -> None:
        preferred = _catalog_product().model_copy(
            update={
                "sku": "preferred",
                "doc_id": "CAT-PREFERRED",
                "title": "Aero Black Running Shoes Size 11",
                "category": "Clothing, Shoes & Jewelry",
                "feature_evidence": [
                    "Soft mesh upper with a cushioned supportive footbed"
                ],
                "similarity": 0.7,
            }
        )
        partial = _catalog_product().model_copy(
            update={
                "sku": "partial",
                "doc_id": "CAT-PARTIAL",
                "title": "Basic Black Running Shoes Size 11",
                "category": "Clothing, Shoes & Jewelry",
                "feature_evidence": ["Firm leather upper"],
                "similarity": 0.9,
            }
        )
        tools = _Tools([partial, preferred])
        previous = ShoppingContext(
            product_query="running shoes",
            colors=["blue"],
            sizes=["size 10"],
            materials=["mesh"],
            comfort=["cushioned"],
            resolved_query="running shoes blue size 10 mesh cushioned",
        )

        with patch(
            "graph.interactive.natural_answer_once",
            new=AsyncMock(return_value=None),
        ):
            result = await _run(
                "Actually, black in size 11 and softer",
                tools,
                graph_mode="interactive",
                dialogue_context={
                    "budget_max": 80.0,
                    "shopping_context": previous,
                },
            )

        query, filters = tools.rag_calls[0]
        self.assertEqual(query, "running shoes")
        self.assertEqual(filters["price_max"], 80.0)
        self.assertEqual(
            tools.web_calls,
            [("running shoes black size 11 mesh soft cushioned", 12)],
        )
        self.assertEqual(result.products[0].private.doc_id, "CAT-PREFERRED")
        self.assertEqual(result.shopping_context.colors, ["black"])
        self.assertEqual(result.shopping_context.sizes, ["size 11"])
        self.assertIn("Aero Black Running Shoes", result.answer_text)
        self.assertNotIn("Basic Black Running Shoes", result.answer_text)
        self.assertEqual(
            {citation.label for citation in result.citations},
            {"CAT-PREFERRED"},
        )

    async def test_negative_color_followup_excludes_black_and_returns_six(self) -> None:
        black = _catalog_product().model_copy(
            update={
                "sku": "black-backpack",
                "doc_id": "CAT-BLACK-BACKPACK",
                "title": "Everest Deluxe Small Backpack, Black, One Size",
                "category": "Clothing, Shoes & Jewelry",
                "similarity": 0.99,
            }
        )
        non_black = [
            _catalog_product().model_copy(
                update={
                    "sku": f"pink-backpack-{index}",
                    "doc_id": f"CAT-PINK-BACKPACK-{index}",
                    "title": f"Pink Canvas Travel Backpack {index}",
                    "category": "Clothing, Shoes & Jewelry",
                    "similarity": 0.9 - (index / 100),
                }
            )
            for index in range(6)
        ]
        tools = _Tools([black, *non_black])
        previous = ShoppingContext(
            product_query="backpack",
            resolved_query="backpack",
        )

        with patch(
            "graph.interactive.natural_answer_once",
            new=AsyncMock(return_value=None),
        ):
            result = await _run(
                "I don't want black",
                tools,
                graph_mode="interactive",
                dialogue_context={"shopping_context": previous},
            )

        self.assertEqual(tools.rag_calls[0][0], "backpack")
        self.assertEqual(tools.web_calls, [])
        self.assertEqual(result.shopping_context.product_query, "backpack")
        self.assertEqual(result.shopping_context.excluded, ["black"])
        self.assertEqual(len(result.products), 6)
        self.assertTrue(
            all("black" not in product.private.title.casefold() for product in result.products)
        )
        self.assertEqual(
            result.top_recommendation.product_key,
            f"catalog:{result.products[0].private.doc_id}",
        )
        self.assertIn(result.products[0].private.title, result.answer_text)
        self.assertIn(result.top_recommendation.reason, result.answer_text)

    async def test_size_answer_searches_active_product_and_returns_matches(self) -> None:
        catalog_products = [
            _catalog_product().model_copy(
                update={
                    "sku": f"sportswear-{index}",
                    "doc_id": f"CAT-SPORTSWEAR-{index}",
                    "title": (
                        "Men's Sportswear Training Shirt "
                        + ("Medium" if index % 2 == 0 else "Large")
                    ),
                    "category": "Clothing, Shoes & Jewelry",
                    "feature_evidence": ["Lightweight training shirt"],
                }
            )
            for index in range(4)
        ]
        tools = _Tools(catalog_products)
        previous = ShoppingContext(
            product_query="mens sportswear",
            resolved_query="mens sportswear",
        )

        with patch(
            "graph.interactive.natural_answer_once",
            new=AsyncMock(return_value=None),
        ):
            result = await _run(
                "Medium or large?",
                tools,
                graph_mode="interactive",
                dialogue_context={
                    "budget_max": 20.0,
                    "shopping_context": previous,
                },
            )

        self.assertEqual(tools.rag_calls[0][0], "mens sportswear")
        self.assertEqual(tools.rag_calls[0][1]["price_max"], 20.0)
        self.assertEqual(tools.web_calls, [])
        self.assertEqual(len(result.products), 4)
        self.assertNotIn("couldn’t find a grounded match", result.answer_text)
        self.assertEqual(set(result.shopping_context.sizes), {"medium", "large"})

    async def test_closest_grounded_products_survive_when_a_facet_is_unconfirmed(self) -> None:
        catalog_products = [
            _catalog_product().model_copy(
                update={
                    "sku": f"jacket-{index}",
                    "doc_id": f"CAT-JACKET-{index}",
                    "title": f"Men's Running Jacket {index}",
                    "category": "Clothing, Shoes & Jewelry",
                    "feature_evidence": ["Lightweight running layer"],
                }
            )
            for index in range(4)
        ]
        tools = _Tools(catalog_products)
        previous = ShoppingContext(
            product_query="mens running jacket",
            resolved_query="mens running jacket",
        )

        with patch(
            "graph.interactive.natural_answer_once",
            new=AsyncMock(return_value=None),
        ):
            result = await _run(
                "Blue",
                tools,
                graph_mode="interactive",
                dialogue_context={"shopping_context": previous},
            )

        self.assertGreater(len(result.products), 0)
        self.assertIn("Lightweight running layer", result.answer_text)
        self.assertNotIn("closest grounded candidate", result.answer_text)
        self.assertNotIn("matches your", result.answer_text.casefold())
        self.assertNotIn("blue", result.answer_text.casefold())
        self.assertNotIn("does not confirm", result.answer_text)
        self.assertNotIn("couldn’t find a grounded match", result.answer_text)

    async def test_delegation_after_bedding_no_match_keeps_the_product_family(self) -> None:
        catalog_products = [
            _catalog_product().model_copy(
                update={
                    "sku": f"bedding-{index}",
                    "doc_id": f"CAT-BEDDING-{index}",
                    "title": f"Soft Bedding Comforter Set {index}",
                    "category": "Home & Kitchen",
                    "feature_evidence": ["Comforter and pillow set"],
                }
            )
            for index in range(6)
        ]
        tools = _Tools(catalog_products)
        previous = ShoppingContext(
            product_query="bedding",
            resolved_query="bedding",
        )

        with patch(
            "graph.interactive.choose_direction",
            new=AsyncMock(side_effect=AssertionError("must keep bedding context")),
        ):
            result = await _run(
                "Can you just give me give me anything?",
                tools,
                graph_mode="interactive",
                dialogue_context={"shopping_context": previous},
            )

        self.assertEqual(tools.rag_calls[0][0], "bedding")
        self.assertEqual(tools.rag_calls[0][1]["category"], "Home & Kitchen")
        self.assertEqual(len(result.products), 6)
        self.assertNotIn("couldn’t find a grounded match", result.answer_text)

    async def test_spoken_bedding_request_returns_six_catalog_products(self) -> None:
        catalog_products = [
            _catalog_product().model_copy(
                update={
                    "sku": f"spoken-bedding-{index}",
                    "doc_id": f"CAT-SPOKEN-BEDDING-{index}",
                    "title": f"Bedding Comforter and Pillow Set {index}",
                    "category": "Home & Kitchen",
                    "feature_evidence": ["Comforter and pillow set"],
                }
            )
            for index in range(6)
        ]
        tools = _Tools(catalog_products)
        transcript = (
            "Um, I would like some stuff I can use on my bed, like a quilt or "
            "a comforter set or like a pillow, anything like that."
        )

        result = await _run(transcript, tools, graph_mode="interactive")

        self.assertEqual(tools.rag_calls[0][0], "bedding")
        self.assertEqual(tools.rag_calls[0][1]["category"], "Home & Kitchen")
        self.assertEqual(tools.web_calls, [])
        self.assertEqual(len(result.products), 6)

    async def test_greeting_before_grocery_request_still_uses_product_tools(self) -> None:
        tools = _Tools()

        result = await _run(
            "Hello, I need vegetables like broccoli and lettuce",
            tools,
            graph_mode="interactive",
        )

        self.assertEqual(tools.rag_calls[0][0], "vegetables broccoli lettuce")
        self.assertEqual(
            tools.rag_calls[0][1]["category"], "Grocery & Gourmet Food"
        )
        self.assertEqual(len(tools.web_calls), 1)
        self.assertNotIn("thanks for asking", result.answer_text)

    async def test_explicit_new_item_cue_clears_context_in_full_graph(self) -> None:
        tools = _Tools([_catalog_product()])
        previous = ShoppingContext(
            product_query="toy animals",
            colors=["blue"],
            excluded=["black"],
            resolved_query="toy animals blue",
        )

        result = await _run(
            "Also vegetables",
            tools,
            graph_mode="interactive",
            dialogue_context={
                "shopping_context": previous,
                "budget_max": 20.0,
            },
        )

        self.assertEqual(tools.rag_calls[0][0], "vegetables")
        self.assertNotIn("price_max", tools.rag_calls[0][1])
        self.assertEqual(result.shopping_context.product_query, "vegetables")
        self.assertEqual(result.shopping_context.colors, [])
        self.assertEqual(result.shopping_context.excluded, [])
        self.assertFalse(result.shopping_context.is_followup)

    async def test_completed_cart_acknowledgement_skips_full_graph_tools(self) -> None:
        tools = _Tools([_catalog_product()])
        previous = ShoppingContext(
            product_query="vegetables",
            resolved_query="vegetables",
        )

        result = await _run(
            "Okay added cart",
            tools,
            graph_mode="interactive",
            dialogue_context={"shopping_context": previous},
        )

        self.assertEqual(tools.rag_calls, [])
        self.assertEqual(tools.web_calls, [])
        self.assertEqual(result.shopping_context.product_query, "vegetables")
        self.assertIn("shop for next", result.answer_text.casefold())

    async def test_hazardous_mixing_request_stops_before_tools(self) -> None:
        for graph_mode in ("interactive", "llm"):
            for transcript in (
                "Can I mix bleach and ammonia for a stronger cleaner?",
                "mix ammonia with vineager",
            ):
                with self.subTest(graph_mode=graph_mode, transcript=transcript):
                    tools = _Tools()
                    result = await _run(
                        transcript,
                        tools,
                        graph_mode=graph_mode,
                    )

                    self.assertEqual(tools.rag_calls, [])
                    self.assertEqual(tools.web_calls, [])
                    self.assertIn("safety warning", result.answer_text.casefold())

    def test_unknown_graph_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_graph(_Tools(), mode="slow-and-mysterious")


if __name__ == "__main__":
    unittest.main()
