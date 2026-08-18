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
    WebResult,
)
import app.livekit_component as livekit_component
import graph.build
import voice.tts


DEFAULT_TRANSCRIPT = (
    "Compare the current price of the Nerf N Strike Elite Strongarm blaster "
    "with the catalog price."
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
