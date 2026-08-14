"""Repeatable Phase 2 voice-to-voice acceptance check.

Usage:
    python -m app.phase2_acceptance path/to/question.mp3 --runs 3

The recording is never logged. Each run sends it through ASR, the live graph
and MCP tools, then TTS. The harness prints a compact JSON result and exits
non-zero if an integration acceptance criterion fails.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from dotenv import load_dotenv

from graph.build import run_graph
from voice.stt import transcribe
from voice.tts import cap_for_speech, synthesize

REPO_ROOT = Path(__file__).resolve().parents[1]


def _audio_duration(audio: bytes) -> float:
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise RuntimeError("ffprobe is required to measure answer audio")
    with tempfile.NamedTemporaryFile(suffix=".mp3") as output:
        output.write(audio)
        output.flush()
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                output.name,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    return round(float(completed.stdout.strip()), 3)


def run_once(recording: Path, number: int) -> dict:
    started = time.perf_counter()
    transcript = transcribe(recording.read_bytes(), filename=recording.name)
    result = run_graph(transcript)
    answer_audio = synthesize(result.answer_text)
    duration = _audio_duration(answer_audio)

    completed_web_calls = sum(
        step.tool == "web.search" and step.status == "completed"
        for step in result.steps
    )
    has_price_conflict = any(
        conflict.field == "price"
        for product in result.products
        for conflict in product.conflicts
    )
    has_private_citation = any(citation.kind == "private" for citation in result.citations)
    has_live_citation = any(
        citation.kind == "live" and bool(citation.url)
        for citation in result.citations
    )
    exact_spoken_text = cap_for_speech(result.answer_text) == result.answer_text

    checks = {
        "transcript": bool(transcript.strip()),
        "web_search": completed_web_calls > 0,
        "price_conflict": has_price_conflict,
        "private_citation": has_private_citation,
        "live_citation": has_live_citation,
        "exact_spoken_text": exact_spoken_text,
        "audio_at_most_15s": duration <= 15.0,
    }
    return {
        "run": number,
        "passed": all(checks.values()),
        "elapsed_s": round(time.perf_counter() - started, 3),
        "answer_audio_s": duration,
        "web_calls": completed_web_calls,
        "checks": checks,
        "transcript": transcript,
        "answer_text": result.answer_text,
        "private_doc_ids": [
            citation.label for citation in result.citations if citation.kind == "private"
        ],
        "live_urls": [
            citation.url for citation in result.citations if citation.kind == "live"
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording", type=Path)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1:
        raise SystemExit("--runs must be positive")
    if not args.recording.is_file():
        raise SystemExit(f"recording not found: {args.recording}")

    load_dotenv(REPO_ROOT / ".env")
    outcomes = []
    for number in range(1, args.runs + 1):
        outcome = run_once(args.recording, number)
        outcomes.append(outcome)
        print(json.dumps(outcome, ensure_ascii=False), flush=True)
        if not outcome["passed"]:
            raise SystemExit(1)
    print(json.dumps({"runs": args.runs, "all_passed": True}))


if __name__ == "__main__":
    main()
