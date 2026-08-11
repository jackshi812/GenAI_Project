"""Fragment-based speech-to-text using OpenAI transcription."""

from __future__ import annotations

import os

from openai import OpenAI


def transcribe(audio_bytes: bytes, filename: str = "audio.wav") -> str:
    """Return a plain transcript, skipping recordings too small to contain speech."""
    if len(audio_bytes) < 1_024:
        return ""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    response = OpenAI(api_key=api_key).audio.transcriptions.create(
        model=os.getenv("WHISPER_MODEL", "whisper-1"),
        file=(filename, audio_bytes),
    )
    return str(response.text).strip()
