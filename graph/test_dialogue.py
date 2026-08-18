"""Checks for natural, bounded non-product dialogue."""

from __future__ import annotations

import asyncio
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from graph.dialogue import natural_dialogue_reply
from graph.response_style import clarification_reply


class _DialogueLLM:
    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, _messages):
        return SimpleNamespace(
            answer_text=(
                "What would make this most useful at home—organizing, cooking, "
                "decorating, or solving an everyday annoyance?"
            )
        )


class _StaticDialogueLLM:
    def __init__(self, answer_text: str) -> None:
        self.answer_text = answer_text

    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, _messages):
        return SimpleNamespace(answer_text=self.answer_text)


class DialogueTests(unittest.TestCase):
    def test_configured_model_can_generate_contextual_non_template_dialogue(self) -> None:
        with patch.dict(
            os.environ,
            {
                "DIALOGUE_LLM": "1",
                "OPENAI_API_KEY": "test",
                "LLM_PROVIDER": "openai",
            },
        ):
            answer = asyncio.run(
                natural_dialogue_reply(
                    "clarification",
                    "I need something for home",
                    10.0,
                    llm_factory=_DialogueLLM,
                )
            )

        self.assertIn("useful at home", answer)
        self.assertIn("?", answer)
        self.assertLessEqual(len(answer.split()), 30)

    def test_failure_prefaced_clarification_uses_direct_budget_fallback(self) -> None:
        preambles = (
            "I’m sorry, I can’t understand the request. What product do you want under $20?",
            "I couldn’t find a clear direction. What should the item help with under $20?",
            "I’m unable to narrow this down. Who is the item for under $20?",
        )

        for model_answer in preambles:
            with self.subTest(model_answer=model_answer), patch.dict(
                os.environ,
                {
                    "DIALOGUE_LLM": "1",
                    "OPENAI_API_KEY": "test",
                    "LLM_PROVIDER": "openai",
                },
            ):
                answer = asyncio.run(
                    natural_dialogue_reply(
                        "clarification",
                        "I want something under $20",
                        20.0,
                        llm_factory=lambda: _StaticDialogueLLM(model_answer),
                    )
                )

            self.assertEqual(
                answer,
                clarification_reply(20.0, transcript="I want something under $20"),
            )
            self.assertEqual(answer.count("?"), 1)
            self.assertIn("$20", answer)
            self.assertFalse(answer.casefold().startswith(("sorry", "i’m sorry", "i couldn't")))

    def test_failure_prefaced_no_match_uses_direct_budget_fallback(self) -> None:
        preambles = (
            "I couldn’t verify a reliable match. Which requirement should I relax?",
            "I’m sorry, I couldn’t find a match. Which detail can change?",
            "I’m unable to narrow the results. Which feature is flexible?",
        )
        expected = (
            "What would you like to specify while keeping your $20 limit—"
            "product type, brand, or a key feature?"
        )

        for model_answer in preambles:
            with self.subTest(model_answer=model_answer), patch.dict(
                os.environ,
                {
                    "DIALOGUE_LLM": "1",
                    "OPENAI_API_KEY": "test",
                    "LLM_PROVIDER": "openai",
                },
            ):
                answer = asyncio.run(
                    natural_dialogue_reply(
                        "no_match",
                        "Find bananas under $20",
                        20.0,
                        llm_factory=lambda: _StaticDialogueLLM(model_answer),
                    )
                )

            self.assertEqual(answer, expected)
            self.assertEqual(answer.count("?"), 1)
            self.assertIn("$20", answer)
            self.assertNotRegex(
                answer.casefold(),
                r"(?:sorry|couldn['’]?t|unable|no (?:reliable )?match)",
            )

    def test_unavailable_model_uses_a_contextual_claim_free_fallback(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            answer = asyncio.run(
                natural_dialogue_reply(
                    "clarification",
                    "I want something under $10",
                    10.0,
                )
            )

        self.assertIn("$10", answer)
        self.assertIn("?", answer)
        self.assertNotIn("found", answer.casefold())
