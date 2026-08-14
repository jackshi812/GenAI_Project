"""Tests for the displayed-answer/TTS text boundary."""

from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

from voice.tts import cap_for_speech, synthesize


class TextToSpeechBoundaryTests(unittest.TestCase):
    def test_synthesize_sends_the_exact_short_text(self) -> None:
        response = MagicMock()
        response.content = b"mp3"
        client = MagicMock()
        client.audio.speech.create.return_value = response
        answer = "The catalog price is $13.99 and live evidence shows $10.95."

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
            with patch("voice.tts.OpenAI", return_value=client):
                self.assertEqual(synthesize(answer), b"mp3")

        self.assertEqual(client.audio.speech.create.call_args.kwargs["input"], answer)

    def test_synthesize_rejects_uncapped_text(self) -> None:
        answer = " ".join(f"word{index}" for index in range(31))
        self.assertNotEqual(cap_for_speech(answer), answer)
        with self.assertRaisesRegex(ValueError, "30-word"):
            synthesize(answer)

    def test_synthesize_accepts_a_low_latency_model_override(self) -> None:
        response = MagicMock(content=b"mp3")
        client = MagicMock()
        client.audio.speech.create.return_value = response

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test"}, clear=True):
            with patch("voice.tts.OpenAI", return_value=client):
                synthesize("A short grounded answer.", model="tts-1")

        self.assertEqual(
            client.audio.speech.create.call_args.kwargs["model"], "tts-1"
        )


if __name__ == "__main__":
    unittest.main()
