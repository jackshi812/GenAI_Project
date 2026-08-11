"""Command-line smoke test for speech transcription."""

from __future__ import annotations

import sys
from pathlib import Path

from voice.stt import transcribe


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m voice.smoke path/to/recording.wav")
    audio_path = Path(sys.argv[1])
    print(transcribe(audio_path.read_bytes(), filename=audio_path.name))


if __name__ == "__main__":
    main()
