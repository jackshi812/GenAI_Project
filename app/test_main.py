"""Streamlit-level regression check for the graph-to-UI result seam."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from contracts import AssistantResult
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


if __name__ == "__main__":
    unittest.main()
