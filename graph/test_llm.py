"""Configuration checks for the shared language-model factory."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from graph.llm import get_llm


class LlmConfigurationTests(unittest.TestCase):
    def test_gpt5_mini_defaults_to_low_reasoning_for_voice_latency(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "openai",
                "LLM_MODEL": "gpt-5-mini",
                "OPENAI_API_KEY": "test-key",
            },
            clear=True,
        ):
            model = get_llm()

        self.assertEqual(model.reasoning_effort, "low")

    def test_reasoning_effort_can_be_overridden(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "openai",
                "LLM_MODEL": "gpt-5-mini",
                "LLM_REASONING_EFFORT": "minimal",
                "OPENAI_API_KEY": "test-key",
            },
            clear=True,
        ):
            model = get_llm()

        self.assertEqual(model.reasoning_effort, "minimal")

    def test_call_specific_effort_does_not_change_global_default(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "openai",
                "LLM_MODEL": "gpt-5-mini",
                "LLM_REASONING_EFFORT": "low",
                "OPENAI_API_KEY": "test-key",
            },
            clear=True,
        ):
            answer_model = get_llm(reasoning_effort="minimal")
            general_model = get_llm()

        self.assertEqual(answer_model.reasoning_effort, "minimal")
        self.assertEqual(general_model.reasoning_effort, "low")


if __name__ == "__main__":
    unittest.main()
