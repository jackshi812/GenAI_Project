"""Fragment-based text-to-speech with a hard spoken-answer length cap."""

from __future__ import annotations

import os
import re
from pathlib import Path

from openai import OpenAI


def cap_for_speech(text: str, max_words: int = 30) -> str:
    """Limit speech text, preferring the last complete sentence in the cap."""
    if max_words < 1:
        raise ValueError("max_words must be positive")
    words = text.split()
    if len(words) <= max_words:
        return text

    capped = words[:max_words]
    sentence_end = 0
    for index, word in enumerate(capped, start=1):
        if re.search(r"[.!?][\"')\]]*$", word):
            sentence_end = index
    if sentence_end:
        capped = capped[:sentence_end]
    result = " ".join(capped).rstrip(" ,;:-")
    if not re.search(r"[.!?][\"')\]]*$", result):
        result += "."
    return result


def synthesize(text: str) -> bytes:
    """Synthesize a capped answer and return MP3 bytes."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    response = OpenAI(api_key=api_key).audio.speech.create(
        model=os.getenv("TTS_MODEL", "gpt-4o-mini-tts"),
        voice=os.getenv("TTS_VOICE", "alloy"),
        input=cap_for_speech(text),
        response_format="mp3",
    )
    return response.content


def main() -> None:
    answers = (
        "The Buffalo Games Pokémon puzzle is $10.99 in the 2020 catalog, within your $20 budget. The catalog has no rating data.",
        "The LEGO suitcase was $19.78 in the 2020 catalog. Recorded eBay evidence shows $12.95 and a 4.8 rating; verify current availability on the retailer.",
        "The Nerf Strongarm was $13.99 in the 2020 catalog. Recorded eBay evidence shows $21.95 and a 3.5 rating, so the prices conflict.",
    )
    for index, answer in enumerate(answers, start=1):
        spoken = cap_for_speech(answer)
        audio = synthesize(answer)
        output = Path(f"out_{index}.mp3")
        output.write_bytes(audio)
        print(f"{output}: {len(spoken.split())} words, {len(audio)} bytes")


if __name__ == "__main__":
    main()
