"""Streamlit-level regression check for the graph-to-UI result seam."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import call, patch

from streamlit.testing.v1 import AppTest

from contracts import (
    AssistantResult,
    Citation,
    ComparisonProduct,
    Conflict,
    MatchInfo,
    RagResult,
    StepEvent,
    TopRecommendation,
    WebResult,
)
import app.livekit_component as livekit_component
import graph.build
import voice.tts


DEFAULT_TRANSCRIPT = (
    "Compare the current price of the Nerf N Strike Elite Strongarm blaster "
    "with the catalog price."
)


def _cart_products(prefix: str, count: int) -> list[ComparisonProduct]:
    products = []
    for index in range(count):
        private = RagResult(
            sku=f"{prefix.lower()}-sku-{index}",
            title=f"{prefix} Catalog Product {index}",
            price=10.0 + index,
            rating=None,
            brand=f"{prefix} Brand",
            ingredients=None,
            doc_id=f"{prefix.upper()}-{index}",
            image_url=f"https://example.com/{prefix.lower()}-{index}.jpg",
            product_url=f"https://example.com/catalog/{prefix.lower()}-{index}",
            category="Home & Kitchen",
            price_low=10.0 + index,
            price_high=10.0 + index,
            similarity=0.9,
            budget_fit="within",
        )
        live = WebResult(
            title=f"{prefix} Current Product {index}",
            url=f"https://retailer.example/{prefix.lower()}-{index}",
            snippet=f"Grounded {prefix} retailer result {index}.",
            price=20.0 + index,
            availability="In stock",
            image_url=f"https://retailer.example/{prefix.lower()}-{index}.jpg",
            rating=4.0 + (index / 10),
            origin="live_serper",
        )
        products.append(
            ComparisonProduct(
                private=private,
                live=live,
                conflicts=[],
                match=MatchInfo(
                    similarity=0.95,
                    verdict="same",
                    reason="The grounded catalog and web titles match.",
                ),
            )
        )
    return products


def _buttons_with_label(app: AppTest, label: str):
    return [button for button in app.button if button.label == label]


def _button_with_key_fragment(app: AppTest, label: str, fragment: str):
    matches = [
        button
        for button in app.button
        if button.label == label and fragment in str(button.key)
    ]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one {label!r} button containing {fragment!r}; got {matches!r}"
        )
    return matches[0]


def _assert_one_first_card_top_badge(
    test_case: unittest.TestCase,
    app: AppTest,
    first_title: str,
) -> None:
    cards = [
        item.value
        for item in app.markdown
        if '<article class="shopping-card">' in item.value
    ]
    test_case.assertGreaterEqual(len(cards), 1)
    test_case.assertIn(first_title, cards[0])
    test_case.assertIn("Top recommendation", cards[0])
    test_case.assertEqual(
        sum(card.count("Top recommendation") for card in cards),
        1,
    )
    test_case.assertTrue(
        all("Top recommendation" not in card for card in cards[1:])
    )


class GraphResultSeamTests(unittest.TestCase):
    def test_initial_load_waits_for_a_chat_message(self) -> None:
        with patch.object(livekit_component, "live_voice", return_value=None):
            with patch.object(graph.build, "run_graph") as run:
                app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                    timeout=10
                )

        self.assertEqual(list(app.exception), [])
        self.assertEqual(run.call_count, 0)
        self.assertTrue(
            any(
                item.value == "Chat with your store assistant"
                for item in app.subheader
            )
        )
        self.assertEqual(len(app.text_input), 0)

    def test_fast_voice_preview_waits_to_show_product_images(self) -> None:
        product = RagResult(
            sku="pending-product",
            title="Pending product",
            price=12.0,
            rating=None,
            brand=None,
            ingredients=None,
            doc_id="CAT-PENDING",
            image_url="https://example.com/pending.jpg",
            product_url="https://example.com/pending",
            category="Home & Kitchen",
            price_low=12.0,
            price_high=12.0,
            similarity=0.9,
            budget_fit="within",
        )
        fast_event = {
            "type": "fast_reply",
            "event_id": "fast-pending-product",
            "data": {
                "transcript": "Find something useful",
                "answer_text": "A fast preview that should remain hidden.",
                "elapsed_ms": 25,
                "live_followup_needed": True,
                "turn_kind": "catalog",
                "product": product.model_dump(mode="json"),
                "citations": [],
            },
        }

        with patch.object(
            livekit_component,
            "live_voice",
            return_value=fast_event,
        ):
            with patch.object(graph.build, "run_graph") as run:
                app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                    timeout=10
                )

        rendered_markdown = "\n".join(item.value for item in app.markdown)
        self.assertEqual(list(app.exception), [])
        self.assertEqual(run.call_count, 0)
        self.assertNotIn('<article class="shopping-card">', rendered_markdown)
        self.assertTrue(
            any(
                "Give me a moment while I pull up the best matches."
                in item.value
                for item in app.info
            )
        )

    def test_typed_message_runs_the_same_grounded_result_path(self) -> None:
        question = "Find me Pokemon cards under $25"
        result = AssistantResult(
            transcript=question,
            plan="Search grounded product evidence.",
            answer_text="Here are grounded Pokemon card options.",
            products=[],
            steps=[],
            citations=[],
        )
        request_id = "typed-test-1"
        typed_event = {
            "type": "typed_message",
            "event_id": request_id,
            "data": {"transcript": question, "request_id": request_id},
        }

        with patch.object(
            livekit_component, "live_voice", return_value=typed_event
        ):
            with patch.object(graph.build, "run_graph", return_value=result) as run:
                with patch.object(voice.tts, "synthesize", return_value=b"audio"):
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )

        self.assertEqual(list(app.exception), [])
        run.assert_called_once_with(question)
        self.assertEqual(app.session_state.transcript, question)
        self.assertEqual(
            app.session_state.external_turn["answer_text"],
            "Here are grounded Pokemon card options.",
        )
        self.assertEqual(app.session_state.external_turn["request_id"], request_id)
        self.assertEqual(
            app.session_state.external_turn["audio_base64"],
            "YXVkaW8=",
        )
        self.assertEqual(
            app.session_state.external_turn["audio_mime"],
            "audio/mpeg",
        )

    def test_fixture_mode_renders_one_graph_result_and_source_label(self) -> None:
        result = AssistantResult(
            transcript=DEFAULT_TRANSCRIPT,
            plan="Use private and live evidence.",
            answer_text="Grounded answer.",
            products=[],
            steps=[],
            citations=[],
        )
        typed_event = {
            "type": "typed_message",
            "event_id": "fixture-typed-1",
            "data": {
                "transcript": DEFAULT_TRANSCRIPT,
                "request_id": "fixture-typed-1",
            },
        }

        with patch.dict(os.environ, {"TOOL_MODE": "fixture"}, clear=False):
            with patch.object(
                livekit_component, "live_voice", return_value=typed_event
            ):
                with patch.object(graph.build, "run_graph", return_value=result) as run:
                    with patch.object(voice.tts, "synthesize", return_value=b"audio"):
                        app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                            timeout=10
                        )

        self.assertEqual(list(app.exception), [])
        self.assertEqual(run.call_count, 1)
        self.assertTrue(
            any(
                item.value == "Fixture graph · Recorded data"
                for item in app.caption
            )
        )
        self.assertEqual(
            app.session_state.external_turn["answer_text"], "Grounded answer."
        )

    def test_agent_step_log_wraps_complete_details_without_a_dataframe(self) -> None:
        question = "Find a Lego toy"
        long_detail = (
            "query='lego toy' product='lego toy' filters={'category': "
            "'Toys & Games', 'k': 12} -> 6 reliable of 12 retrieved"
        )
        result = AssistantResult(
            transcript=question,
            plan="Search grounded product evidence.",
            answer_text="Here are grounded Lego options.",
            products=[],
            steps=[
                StepEvent(
                    node="retriever",
                    tool="rag.search",
                    started_at="2026-08-20T15:40:00+00:00",
                    duration_ms=524,
                    status="completed",
                    detail=long_detail,
                )
            ],
            citations=[],
        )
        typed_event = {
            "type": "typed_message",
            "event_id": "step-log-layout",
            "data": {
                "transcript": question,
                "request_id": "step-log-layout",
            },
        }

        with patch.object(livekit_component, "live_voice", return_value=typed_event):
            with patch.object(graph.build, "run_graph", return_value=result):
                with patch.object(voice.tts, "synthesize", return_value=b"audio"):
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )

        self.assertEqual(list(app.exception), [])
        self.assertEqual(len(app.dataframe), 0)
        self.assertTrue(
            any("1. retriever" in item.value for item in app.markdown)
        )
        self.assertIn(long_detail, [item.value for item in app.caption])

    def test_result_renders_as_one_unified_shopping_card(self) -> None:
        private = RagResult(
            sku="test-sku",
            title="Catalog product title",
            price=12.99,
            rating=None,
            brand="Test Brand",
            ingredients=None,
            doc_id="AMZ-TEST",
            image_url="https://example.com/catalog.jpg",
            product_url="https://example.com/catalog",
            category="Toys & Games",
            price_low=12.99,
            price_high=12.99,
            similarity=0.9,
            budget_fit="within",
        )
        live = WebResult(
            title="Current product title",
            url="https://example.com/current",
            snippet="Current retailer result.",
            price=15.49,
            availability="In stock",
            image_url="https://example.com/current.jpg",
            rating=4.7,
            origin="live_serper",
        )
        product = ComparisonProduct(
            private=private,
            live=live,
            conflicts=[
                Conflict(
                    field="price",
                    private_value=12.99,
                    live_value=15.49,
                    note="price rose",
                )
            ],
            match=MatchInfo(
                similarity=0.95,
                verdict="same",
                reason="Titles match.",
            ),
        )
        question = "Show me the current product"
        result = AssistantResult(
            transcript=question,
            plan="Use catalog and web evidence.",
            answer_text="Here is the grounded result.",
            products=[product],
            steps=[],
            citations=[],
        )
        typed_event = {
            "type": "typed_message",
            "event_id": "shopping-card-test",
            "data": {
                "transcript": question,
                "request_id": "shopping-card-test",
            },
        }

        with patch.object(
            livekit_component, "live_voice", return_value=typed_event
        ):
            with patch.object(graph.build, "run_graph", return_value=result):
                with patch.object(voice.tts, "synthesize", return_value=b"audio"):
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )

        rendered_markdown = "\n".join(item.value for item in app.markdown)
        self.assertEqual(list(app.exception), [])
        self.assertIn('<article class="shopping-card">', rendered_markdown)
        self.assertEqual(
            rendered_markdown.count('<article class="shopping-card">'), 1
        )
        self.assertIn(">Catalog</span>", rendered_markdown)
        self.assertIn(">Web search</span>", rendered_markdown)
        self.assertTrue(any(item.value == "Results" for item in app.subheader))

    def test_six_cards_have_ordered_native_cart_actions_and_added_state(self) -> None:
        products = _cart_products("First", 8)
        question = "Show me grounded first products"
        result = AssistantResult(
            transcript=question,
            plan="Search grounded product evidence.",
            answer_text="Here are the first grounded products.",
            products=products,
            steps=[],
            citations=[],
            top_recommendation=TopRecommendation(
                product_key="catalog:FIRST-0",
                title=products[0].live.title,
                reason="The graph ranked this grounded product first.",
            ),
        )
        event = {
            "type": "typed_message",
            "event_id": "cart-six-products",
            "data": {"transcript": question, "request_id": "cart-six-products"},
        }

        with patch.object(livekit_component, "live_voice", return_value=event):
            with patch.object(graph.build, "run_graph", return_value=result) as run:
                with patch.object(voice.tts, "synthesize", return_value=b"audio") as tts:
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "First Current Product 0",
                    )
                    add_buttons = _buttons_with_label(app, "Add to cart")
                    self.assertEqual(len(add_buttons), 6)
                    self.assertEqual(
                        [button.key for button in add_buttons],
                        [
                            f"cart-add-{index}-catalog:FIRST-{index}"
                            for index in range(6)
                        ],
                    )

                    app = add_buttons[2].click().run(timeout=10)
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "First Current Product 0",
                    )
                    app = _button_with_key_fragment(
                        app,
                        "Add to cart",
                        "catalog:FIRST-0",
                    ).click().run(timeout=10)
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "First Current Product 0",
                    )

        self.assertEqual(list(app.exception), [])
        self.assertEqual(run.call_count, 1)
        self.assertEqual(tts.call_count, 1)
        self.assertEqual(
            app.session_state.cart_products,
            [products[2], products[0]],
        )
        self.assertEqual(len(_buttons_with_label(app, "Add to cart")), 4)
        added_buttons = _buttons_with_label(app, "Added ✓")
        self.assertEqual(len(added_buttons), 2)
        self.assertTrue(all(button.disabled for button in added_buttons))
        rendered_markdown = "\n".join(
            item.value
            for item in app.markdown
            if '<article class="shopping-card">' in item.value
        )
        positions = [
            rendered_markdown.index(f"First Current Product {index}")
            for index in range(6)
        ]
        self.assertEqual(positions, sorted(positions))

    def test_evidence_less_product_has_only_a_disabled_unavailable_action(self) -> None:
        product = ComparisonProduct(
            private=None,
            live=None,
            conflicts=[],
            match=None,
        )
        question = "Show a product without grounded identity"
        result = AssistantResult(
            transcript=question,
            plan="Expose an incomplete comparison safely.",
            answer_text="No grounded product identity is available.",
            products=[product],
            steps=[],
            citations=[],
        )
        event = {
            "type": "typed_message",
            "event_id": "cart-unavailable-product",
            "data": {
                "transcript": question,
                "request_id": "cart-unavailable-product",
            },
        }

        with patch.object(livekit_component, "live_voice", return_value=event):
            with patch.object(graph.build, "run_graph", return_value=result):
                with patch.object(voice.tts, "synthesize", return_value=b"audio"):
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )

        self.assertEqual(list(app.exception), [])
        unavailable = _buttons_with_label(app, "Unavailable")
        self.assertEqual(len(unavailable), 1)
        self.assertTrue(unavailable[0].disabled)
        self.assertEqual(_buttons_with_label(app, "Add to cart"), [])
        self.assertEqual(app.session_state.cart_products, [])

    def test_cart_uses_plain_text_and_origin_specific_price_labels(self) -> None:
        origin_products = []
        expected_labels = {
            "live_serper": "Current web price: $20.00",
            "recorded_fixture": "Recorded web price: $21.00",
            "unknown": "Web price: $22.00",
        }
        for index, (origin, _) in enumerate(expected_labels.items()):
            live = _cart_products("Origin", 3)[index].live.model_copy(
                update={
                    "title": f"Origin {origin}",
                    "origin": origin,
                }
            )
            origin_products.append(
                ComparisonProduct(
                    private=None,
                    live=live,
                    conflicts=[],
                    match=None,
                )
            )

        unsafe_title = "**Literal title** <script>not markup</script>"
        unsafe_price = "[Not a link](https://evil.example)"
        safe_listing = (
            "https://catalog.example/item?campaign=%22safe%22&slot=1"
        )
        raw_private = _cart_products("Raw", 1)[0].private.model_copy(
            update={
                "title": unsafe_title,
                "price": unsafe_price,
                "price_low": None,
                "price_high": None,
                "image_url": "javascript:alert('not-an-image')",
                "product_url": safe_listing,
            }
        )
        raw_product = ComparisonProduct(
            private=raw_private,
            live=None,
            conflicts=[],
            match=None,
        )

        with patch.object(livekit_component, "live_voice", return_value=None):
            app = AppTest.from_file(Path(__file__).with_name("main.py"))
            app.session_state.cart_products = [*origin_products, raw_product]
            app = app.run(timeout=10)

        self.assertEqual(list(app.exception), [])
        rendered_text = [item.value for item in app.text]
        for expected_label in expected_labels.values():
            self.assertIn(expected_label, rendered_text)
        self.assertIn(unsafe_title, rendered_text)
        self.assertIn(f"2020 catalog price: {unsafe_price}", rendered_text)
        self.assertIn("Sources: Catalog", rendered_text)

        rendered_markdown = "\n".join(item.value for item in app.markdown)
        self.assertNotIn(unsafe_title, rendered_markdown)
        self.assertNotIn(unsafe_price, rendered_markdown)
        self.assertNotIn("Sources: Catalog", rendered_markdown)
        self.assertIn("Estimated total (3 items): $63.00", rendered_markdown)

        rendered_captions = "\n".join(item.value for item in app.caption)
        self.assertIn(
            "Current web price + Recorded web price + Web price",
            rendered_captions,
        )
        self.assertIn(
            "1 item was not included because the displayed price is missing "
            "or non-numeric.",
            rendered_captions,
        )

        grounded_links = app.get("link_button")
        self.assertEqual(len(grounded_links), 4)
        self.assertTrue(
            all(link.proto.label == "View grounded listing" for link in grounded_links)
        )
        grounded_urls = [link.proto.url for link in grounded_links]
        self.assertIn(safe_listing, grounded_urls)
        self.assertFalse(any("evil.example" in url for url in grounded_urls))
        self.assertEqual(len(app.image), 3)
        self.assertTrue(
            all(image.value for image in app.image),
            "Each grounded cart thumbnail should have a rendered image URL.",
        )

    def test_cart_persists_across_restart_and_search_without_voice_side_effects(self) -> None:
        first_products = _cart_products("Alpha", 6)
        second_products = _cart_products("Beta", 3)
        voice_products = _cart_products("Voice", 2)
        first_question = "Show alpha products"
        second_question = "Show beta products"
        first_result = AssistantResult(
            transcript=first_question,
            plan="Search alpha products.",
            answer_text="Here are grounded alpha products.",
            products=first_products,
            steps=[],
            citations=[],
            top_recommendation=TopRecommendation(
                product_key="catalog:ALPHA-0",
                title=first_products[0].live.title,
                reason="The graph ranked this grounded alpha product first.",
            ),
        )
        second_result = AssistantResult(
            transcript=second_question,
            plan="Search beta products.",
            answer_text="Here are grounded beta products.",
            products=second_products,
            steps=[],
            citations=[],
            top_recommendation=TopRecommendation(
                product_key="catalog:BETA-0",
                title=second_products[0].live.title,
                reason="The graph ranked this grounded beta product first.",
            ),
        )
        voice_result = AssistantResult(
            transcript="Show voice products",
            plan="Receive grounded voice products.",
            answer_text="Here are grounded voice products.",
            products=voice_products,
            steps=[],
            citations=[],
            top_recommendation=TopRecommendation(
                product_key="catalog:VOICE-0",
                title=voice_products[0].live.title,
                reason="The graph ranked this grounded voice product first.",
            ),
        )
        first_event = {
            "type": "typed_message",
            "event_id": "cart-alpha-search",
            "data": {"transcript": first_question, "request_id": "cart-alpha-search"},
        }
        restart_event = {
            "type": "restart_chat",
            "event_id": "cart-restart",
            "data": {},
        }
        second_event = {
            "type": "typed_message",
            "event_id": "cart-beta-search",
            "data": {"transcript": second_question, "request_id": "cart-beta-search"},
        }
        voice_event = {
            "type": "assistant_result",
            "event_id": "cart-voice-search",
            "data": voice_result.model_dump(mode="json"),
        }

        with patch.object(
            livekit_component,
            "live_voice",
            return_value=first_event,
        ) as live:
            with patch.object(
                graph.build,
                "run_graph",
                side_effect=[first_result, second_result],
            ) as run:
                with patch.object(voice.tts, "synthesize", return_value=b"audio") as tts:
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "Alpha Current Product 0",
                    )
                    app = _button_with_key_fragment(
                        app,
                        "Add to cart",
                        "catalog:ALPHA-2",
                    ).click().run(timeout=10)
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "Alpha Current Product 0",
                    )
                    app = _button_with_key_fragment(
                        app,
                        "Add to cart",
                        "catalog:ALPHA-0",
                    ).click().run(timeout=10)
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "Alpha Current Product 0",
                    )
                    self.assertEqual(run.call_count, 1)
                    self.assertEqual(tts.call_count, 1)

                    live.return_value = restart_event
                    app = app.run(timeout=10)
                    self.assertEqual(
                        app.session_state.cart_products,
                        [first_products[2], first_products[0]],
                    )
                    self.assertIsNone(app.session_state.assistant_result)
                    self.assertEqual(run.call_count, 1)
                    self.assertEqual(tts.call_count, 1)
                    self.assertEqual(
                        len(
                            [
                                expander
                                for expander in app.expander
                                if expander.label == "Cart (2)"
                            ]
                        ),
                        1,
                    )
                    restart_text = "\n".join(item.value for item in app.text)
                    self.assertIn("Alpha Current Product 2", restart_text)
                    self.assertIn("Alpha Current Product 0", restart_text)

                    live.return_value = second_event
                    app = app.run(timeout=10)
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "Beta Current Product 0",
                    )
                    self.assertEqual(len(_buttons_with_label(app, "Add to cart")), 3)
                    self.assertEqual(
                        app.session_state.cart_products,
                        [first_products[2], first_products[0]],
                    )
                    self.assertEqual(run.call_count, 2)
                    self.assertEqual(tts.call_count, 2)

                    preserved_search_state = (
                        app.session_state.transcript,
                        app.session_state.assistant_result,
                        app.session_state.external_turn,
                        app.session_state.answer_audio,
                        app.session_state.last_component_event_id,
                    )
                    app = _button_with_key_fragment(
                        app,
                        "Add to cart",
                        "catalog:BETA-1",
                    ).click().run(timeout=10)
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "Beta Current Product 0",
                    )
                    self.assertEqual(
                        app.session_state.cart_products,
                        [first_products[2], first_products[0], second_products[1]],
                    )
                    self.assertEqual(run.call_count, 2)
                    self.assertEqual(tts.call_count, 2)
                    self.assertEqual(
                        (
                            app.session_state.transcript,
                            app.session_state.assistant_result,
                            app.session_state.external_turn,
                            app.session_state.answer_audio,
                            app.session_state.last_component_event_id,
                        ),
                        preserved_search_state,
                    )

                    rendered_cart_text = "\n".join(
                        [item.value for item in app.text]
                        + [item.value for item in app.caption]
                    )
                    self.assertIn("Alpha Current Product 2", rendered_cart_text)
                    self.assertIn("Alpha Current Product 0", rendered_cart_text)
                    self.assertIn("Beta Current Product 1", rendered_cart_text)
                    self.assertIn("Current web price: $22.00", rendered_cart_text)
                    self.assertIn("Current web price: $20.00", rendered_cart_text)
                    self.assertIn("Current web price: $21.00", rendered_cart_text)
                    self.assertEqual(
                        rendered_cart_text.count("Sources: Catalog + Web search"),
                        3,
                    )
                    grounded_urls = [
                        link.proto.url for link in app.get("link_button")
                    ]
                    self.assertIn(
                        "https://retailer.example/alpha-2",
                        grounded_urls,
                    )
                    self.assertIn(
                        "https://retailer.example/beta-1",
                        grounded_urls,
                    )
                    self.assertNotIn("Subtotal", rendered_cart_text)
                    self.assertFalse(
                        any("checkout" in button.label.casefold() for button in app.button)
                    )

                    live.return_value = voice_event
                    app = app.run(timeout=10)
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "Voice Current Product 0",
                    )
                    self.assertEqual(
                        app.session_state.cart_products,
                        [first_products[2], first_products[0], second_products[1]],
                    )
                    self.assertEqual(app.session_state.assistant_result, voice_result)
                    self.assertEqual(run.call_count, 2)
                    self.assertEqual(tts.call_count, 2)
                    preserved_search_state = (
                        app.session_state.transcript,
                        app.session_state.assistant_result,
                        app.session_state.external_turn,
                        app.session_state.answer_audio,
                        app.session_state.last_component_event_id,
                    )

                    app = _button_with_key_fragment(
                        app,
                        "Remove",
                        "catalog:ALPHA-2",
                    ).click().run(timeout=10)
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "Voice Current Product 0",
                    )
                    self.assertEqual(
                        app.session_state.cart_products,
                        [first_products[0], second_products[1]],
                    )
                    self.assertEqual(run.call_count, 2)
                    self.assertEqual(tts.call_count, 2)
                    self.assertEqual(
                        (
                            app.session_state.transcript,
                            app.session_state.assistant_result,
                            app.session_state.external_turn,
                            app.session_state.answer_audio,
                            app.session_state.last_component_event_id,
                        ),
                        preserved_search_state,
                    )

                    app = _buttons_with_label(app, "Clear cart")[0].click().run(
                        timeout=10
                    )
                    _assert_one_first_card_top_badge(
                        self,
                        app,
                        "Voice Current Product 0",
                    )

        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.session_state.cart_products, [])
        self.assertEqual(len(_buttons_with_label(app, "Add to cart")), 2)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(tts.call_count, 2)
        self.assertEqual(
            (
                app.session_state.transcript,
                app.session_state.assistant_result,
                app.session_state.external_turn,
                app.session_state.answer_audio,
                app.session_state.last_component_event_id,
            ),
            preserved_search_state,
        )
        cart_expanders = [
            expander for expander in app.expander if expander.label == "Cart (0)"
        ]
        self.assertEqual(len(cart_expanders), 1)

    def test_clarification_turn_replaces_the_empty_result_error(self) -> None:
        question = "I want something under 20 bucks"
        result = AssistantResult(
            transcript=question,
            plan=(
                "Clarifying question; product tools paused until the shopper "
                "names a category or use case."
            ),
            answer_text="What kind of product sounds best?",
            products=[],
            steps=[],
            citations=[],
        )
        typed_event = {
            "type": "typed_message",
            "event_id": "clarification-test",
            "data": {
                "transcript": question,
                "request_id": "clarification-test",
            },
        }

        with patch.object(
            livekit_component, "live_voice", return_value=typed_event
        ):
            with patch.object(graph.build, "run_graph", return_value=result):
                with patch.object(voice.tts, "synthesize", return_value=b"audio"):
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )

        self.assertEqual(list(app.exception), [])
        self.assertTrue(
            any("Tell me a little more" in item.value for item in app.info)
        )
        self.assertFalse(
            any("No grounded product results" in item.value for item in app.info)
        )
        self.assertTrue(
            any(
                item.value == "Clarification needed · Search not started"
                for item in app.caption
            )
        )

    def test_typed_followup_keeps_the_budget_from_clarification(self) -> None:
        vague = "I want something under 20 bucks"
        followup = "a toy"
        clarification = AssistantResult(
            transcript=vague,
            plan=(
                "Clarifying question; product tools paused until the shopper "
                "names a category or use case."
            ),
            answer_text="What kind of product sounds best?",
            products=[],
            steps=[],
            citations=[],
        )
        narrowed = AssistantResult(
            transcript="a toy under $20",
            plan="Search the catalog.",
            answer_text="Oh, I found a grounded toy within your $20 budget.",
            products=[],
            steps=[],
            citations=[],
        )
        first_event = {
            "type": "typed_message",
            "event_id": "vague-turn",
            "data": {"transcript": vague, "request_id": "vague-turn"},
        }
        second_event = {
            "type": "typed_message",
            "event_id": "narrowed-turn",
            "data": {"transcript": followup, "request_id": "narrowed-turn"},
        }

        with patch.object(
            livekit_component, "live_voice", return_value=first_event
        ) as live:
            with patch.object(
                graph.build,
                "run_graph",
                side_effect=[clarification, narrowed],
            ) as run:
                with patch.object(voice.tts, "synthesize", return_value=b"audio"):
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )
                    live.return_value = second_event
                    app.run(timeout=10)

        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            run.call_args_list,
            [call(vague), call("a toy under $20")],
        )
        self.assertEqual(app.session_state.transcript, followup)
        self.assertIsNone(app.session_state.pending_budget_max)

    def test_typed_followup_keeps_both_budget_range_bounds(self) -> None:
        vague = "I want something between $50 and $100"
        followup = "a lego toy"
        clarification = AssistantResult(
            transcript=vague,
            plan=(
                "Clarifying question; product tools paused until the shopper "
                "names a category or use case."
            ),
            answer_text="What kind of product sounds best?",
            products=[],
            steps=[],
            citations=[],
        )
        narrowed = AssistantResult(
            transcript="a lego toy between $50 and $100",
            plan="Search the catalog.",
            answer_text="Top recommendation pending grounded results.",
            products=[],
            steps=[],
            citations=[],
        )
        first_event = {
            "type": "typed_message",
            "event_id": "range-turn",
            "data": {"transcript": vague, "request_id": "range-turn"},
        }
        second_event = {
            "type": "typed_message",
            "event_id": "range-followup",
            "data": {"transcript": followup, "request_id": "range-followup"},
        }

        with patch.object(
            livekit_component, "live_voice", return_value=first_event
        ) as live:
            with patch.object(
                graph.build,
                "run_graph",
                side_effect=[clarification, narrowed],
            ) as run:
                with patch.object(voice.tts, "synthesize", return_value=b"audio"):
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )
                    live.return_value = second_event
                    app.run(timeout=10)

        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            run.call_args_list,
            [call(vague), call("a lego toy between $50 and $100")],
        )
        self.assertEqual(app.session_state.active_budget_min, 50.0)
        self.assertEqual(app.session_state.active_budget_max, 100.0)
        self.assertIsNone(app.session_state.pending_budget_min)
        self.assertIsNone(app.session_state.pending_budget_max)

    def test_rejection_then_delegation_keeps_context_and_renders_six(self) -> None:
        question = "Find a puzzle under $20"
        rejection = "I don't like them"
        delegation = "I don't know, help me decide"
        private = RagResult(
            sku="puzzle",
            title="Buffalo Games 500 Piece Jigsaw Puzzle",
            price=10.99,
            rating=None,
            brand="Buffalo Games",
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
        product = ComparisonProduct(
            private=private,
            live=None,
            conflicts=[],
            match=None,
        )
        citation = Citation(kind="private", label="CAT-PUZZLE", url=None)
        first_result = AssistantResult(
            transcript=question,
            plan="Search the catalog.",
            answer_text="Buffalo Games is a promising option under $20.",
            products=[product],
            steps=[],
            citations=[citation],
        )
        refinement = AssistantResult(
            transcript="I don't like them under $20",
            plan=(
                "Preference refinement; previous results retained and product "
                "tools paused until the shopper says what should change."
            ),
            answer_text=(
                "Got it—let’s change direction. What should I adjust: the "
                "product type, brand, or a specific feature?"
            ),
            products=[product],
            steps=[],
            citations=[citation],
        )
        decided_products = [
            ComparisonProduct(
                private=private.model_copy(
                    update={
                        "sku": f"storage-{index}",
                        "doc_id": f"CAT-STORAGE-{index}",
                        "title": f"Home Storage Bin {index}",
                        "category": "Home & Kitchen",
                    }
                ),
                live=None,
                conflicts=[],
                match=None,
            )
            for index in range(9)
        ]
        decided = AssistantResult(
            transcript="I don't know, help me decide under $20",
            plan="Agent-selected direction (llm): search the private catalog.",
            answer_text="Home Storage Bin 0 is a useful option under $20.",
            products=decided_products,
            steps=[],
            citations=[
                Citation(
                    kind="private",
                    label="CAT-STORAGE-0",
                    url=None,
                )
            ],
        )
        first_event = {
            "type": "typed_message",
            "event_id": "product-turn",
            "data": {"transcript": question, "request_id": "product-turn"},
        }
        second_event = {
            "type": "typed_message",
            "event_id": "rejection-turn",
            "data": {"transcript": rejection, "request_id": "rejection-turn"},
        }
        third_event = {
            "type": "typed_message",
            "event_id": "delegation-turn",
            "data": {"transcript": delegation, "request_id": "delegation-turn"},
        }

        with patch.object(
            livekit_component, "live_voice", return_value=first_event
        ) as live:
            with patch.object(
                graph.build,
                "run_graph",
                side_effect=[first_result, refinement, decided],
            ) as run:
                with patch.object(voice.tts, "synthesize", return_value=b"audio"):
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )
                    live.return_value = second_event
                    app.run(timeout=10)
                    self.assertEqual(app.session_state.pending_budget_max, 20.0)
                    self.assertTrue(
                        any(
                            "previous results" in item.value.casefold()
                            for item in app.info
                        )
                    )
                    live.return_value = third_event
                    app.run(timeout=10)

        self.assertEqual(list(app.exception), [])
        self.assertEqual(run.call_args_list[0], call(question))
        second_call = run.call_args_list[1]
        self.assertEqual(second_call.args, ("I don't like them under $20",))
        self.assertEqual(
            second_call.kwargs["dialogue_context"]["products"],
            [product],
        )
        third_call = run.call_args_list[2]
        self.assertEqual(
            third_call.args,
            ("I don't know, help me decide under $20",),
        )
        self.assertTrue(third_call.kwargs["dialogue_context"]["rejected_previous"])
        self.assertEqual(
            third_call.kwargs["dialogue_context"]["avoid_categories"],
            ["Toys & Games"],
        )
        self.assertEqual(
            app.session_state.assistant_result.products,
            decided_products,
        )
        self.assertEqual(app.session_state.transcript, delegation)
        rendered_markdown = "\n".join(item.value for item in app.markdown)
        self.assertEqual(rendered_markdown.count('<article class="shopping-card">'), 6)
        title_positions = [
            rendered_markdown.index(f"Home Storage Bin {index}")
            for index in range(6)
        ]
        self.assertEqual(title_positions, sorted(title_positions))
        self.assertNotIn("Home Storage Bin 6", rendered_markdown)
        captions = [item.value for item in app.caption]
        self.assertNotIn("Live MCP · Catalog only (web not requested)", captions)
        self.assertNotIn(
            "Check each product page for current availability and buying options.",
            captions,
        )

    def test_typed_preference_change_carries_product_budget_and_facets(self) -> None:
        from contracts import ShoppingContext

        first_question = "Find blue running shoes in size 10 under $80"
        followup = "Actually, black in size 11"
        private = RagResult(
            sku="shoe",
            title="Blue Running Shoes Size 10",
            price=59.99,
            rating=None,
            brand=None,
            ingredients=None,
            doc_id="CAT-SHOE",
            image_url="https://example.com/shoe.jpg",
            product_url="https://example.com/shoe",
            category="Clothing, Shoes & Jewelry",
            price_low=59.99,
            price_high=59.99,
            similarity=0.9,
            budget_fit="within",
            feature_evidence=["Cushioned mesh upper"],
        )
        product = ComparisonProduct(
            private=private,
            live=None,
            conflicts=[],
            match=None,
        )
        first_context = ShoppingContext(
            product_query="running shoes",
            colors=["blue"],
            sizes=["size 10"],
            resolved_query="running shoes blue size 10",
        )
        second_context = ShoppingContext(
            product_query="running shoes",
            colors=["black"],
            sizes=["size 11"],
            resolved_query="running shoes black size 11",
            is_followup=True,
        )
        first_result = AssistantResult(
            transcript=first_question,
            plan="Search catalog.",
            answer_text="Here are grounded options.",
            products=[product],
            steps=[],
            citations=[Citation(kind="private", label="CAT-SHOE", url=None)],
            shopping_context=first_context,
        )
        second_result = first_result.model_copy(
            update={
                "transcript": f"{followup} under $80",
                "answer_text": "I reranked the options using black and size 11.",
                "shopping_context": second_context,
            }
        )
        first_event = {
            "type": "typed_message",
            "event_id": "shoe-initial",
            "data": {"transcript": first_question, "request_id": "shoe-initial"},
        }
        second_event = {
            "type": "typed_message",
            "event_id": "shoe-followup",
            "data": {"transcript": followup, "request_id": "shoe-followup"},
        }

        with patch.object(livekit_component, "live_voice", return_value=first_event) as live:
            with patch.object(
                graph.build,
                "run_graph",
                side_effect=[first_result, second_result],
            ) as run:
                with patch.object(voice.tts, "synthesize", return_value=b"audio"):
                    app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                        timeout=10
                    )
                    live.return_value = second_event
                    app.run(timeout=10)

        self.assertEqual(list(app.exception), [])
        second_call = run.call_args_list[1]
        self.assertEqual(second_call.args, (f"{followup} under $80",))
        self.assertEqual(
            second_call.kwargs["dialogue_context"]["shopping_context"],
            first_context,
        )
        self.assertEqual(second_call.kwargs["dialogue_context"]["budget_max"], 80.0)
        self.assertEqual(app.session_state.active_shopping_context, second_context)


if __name__ == "__main__":
    unittest.main()
