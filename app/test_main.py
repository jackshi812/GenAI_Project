"""Streamlit-level regression check for the graph-to-UI result seam."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from contracts import AssistantResult
import graph.build


DEFAULT_TRANSCRIPT = (
    "Compare the current price of the Nerf N Strike Elite Strongarm blaster "
    "with the catalog price."
)


class GraphResultSeamTests(unittest.TestCase):
    def test_initial_load_waits_for_a_recording(self) -> None:
        with patch.object(graph.build, "run_graph") as run:
            app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                timeout=10
            )

        self.assertEqual(list(app.exception), [])
        self.assertEqual(run.call_count, 0)
        self.assertTrue(
            any("Start the conversation" in item.value for item in app.info)
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

        with patch.dict(os.environ, {"TOOL_MODE": "fixture"}, clear=False):
            with patch.object(graph.build, "run_graph", return_value=result) as run:
                app = AppTest.from_file(Path(__file__).with_name("main.py")).run(
                    timeout=10
                )
                app.session_state.transcript = DEFAULT_TRANSCRIPT
                app.run(timeout=10)

        self.assertEqual(list(app.exception), [])
        self.assertEqual(run.call_count, 1)
        self.assertTrue(
            any(
                item.value == "Source mode: Fixture graph · Recorded data"
                for item in app.caption
            )
        )
        self.assertTrue(
            any("Grounded answer." in item.value for item in app.markdown)
        )


if __name__ == "__main__":
    unittest.main()
