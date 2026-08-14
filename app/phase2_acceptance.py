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
import re
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
CANONICAL_DOC_ID = "AMZ-7E4E86AE"
CANONICAL_TRANSCRIPT_TERMS = frozenset({"nerf", "strongarm", "price"})


def _number_is_mentioned(text: str, value: float | str | None) -> bool:
    if not isinstance(value, (int, float)):
        return False
    forms = {f"{float(value):.2f}", f"{float(value):g}"}
    return any(
        re.search(rf"(?<!\d){re.escape(form)}(?!\d)", text)
        for form in forms
    )


def _numeric_claims_are_grounded(
    answer: str, product,
) -> bool:
    """Reject answer numbers that do not occur in the canonical evidence."""
    allowed = {2020.0}
    candidates = (
        product.private.price,
        product.private.price_low,
        product.private.price_high,
        product.live.price if product.live else None,
        product.live.rating if product.live else None,
    )
    allowed.update(
        float(value)
        for value in candidates
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    )
    claims = [
        float(value)
        for value in re.findall(
            r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)(?![A-Za-z0-9])",
            answer,
        )
    ]
    return all(any(abs(claim - value) < 0.001 for value in allowed) for claim in claims)


def _price_claims_are_grounded(answer: str, product) -> bool:
    """Require every currency-marked value to be a catalog or live price."""
    allowed = {
        float(value)
        for value in (
            product.private.price,
            product.private.price_low,
            product.private.price_high,
            product.live.price if product.live else None,
        )
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    claims = [float(value) for value in re.findall(r"\$\s*(\d+(?:\.\d+)?)", answer)]
    return all(any(abs(claim - value) < 0.001 for value in allowed) for claim in claims)


def _source_price_claims_are_grounded(
    answer: str, markers: str, value: float | str | None
) -> bool:
    """Validate every price attributed to one source within a clause."""
    if not isinstance(value, (int, float)):
        return False
    price = r"\$?\s*(\d+(?:\.\d+)?)(?!\d)"
    gap = r"[^$.;!?]*"
    claims = [
        float(match)
        for pattern in (
            rf"\b(?:{markers})\b{gap}{price}",
            rf"{price}{gap}\b(?:{markers})\b",
        )
        for match in re.findall(pattern, answer, re.IGNORECASE)
    ]
    return bool(claims) and all(abs(claim - float(value)) < 0.001 for claim in claims)


def _price_sources_are_grounded(answer: str, product) -> bool:
    if product.live is None:
        return False
    return _source_price_claims_are_grounded(
        answer, r"catalog|2020|private", product.private.price_low
    ) and _source_price_claims_are_grounded(
        answer, r"live|current|currently|now", product.live.price
    )


def _rating_claims_are_grounded(answer: str, product) -> bool:
    """Validate numbers explicitly described as ratings against live evidence."""
    patterns = (
        r"\brating\b[^.;!?\d]{0,40}(\d+(?:\.\d+)?)",
        r"\brated\s+(\d+(?:\.\d+)?)",
        r"(?<![A-Za-z0-9])(\d+(?:\.\d+)?)\s*(?:stars?\b|★|\brating\b)",
    )
    claims = [
        float(value)
        for pattern in patterns
        for value in re.findall(pattern, answer, flags=re.IGNORECASE)
    ]
    if not claims:
        return True
    rating = product.live.rating if product.live else None
    return isinstance(rating, (int, float)) and all(
        abs(claim - float(rating)) < 0.001 for claim in claims
    )


def _availability_claims_are_grounded(answer: str, product) -> bool:
    """Require claimed availability state to agree with matched evidence."""
    if product.live is None:
        evidence = ""
    else:
        evidence = " ".join(
            part
            for part in (product.live.availability, product.live.snippet)
            if part
        ).casefold()
    def states(text: str) -> set[str]:
        states_found = set()
        groups = {
            "negative": (
                "out of stock",
                "sold out",
                "backordered",
                "back ordered",
                "on backorder",
                "unavailable",
                "not available",
            ),
            "positive": ("in stock", "available"),
            "shipping": ("delivery", "shipping", "ships"),
        }
        for state, phrases in groups.items():
            if any(re.search(rf"\b{re.escape(phrase)}\b", text) for phrase in phrases):
                states_found.add(state)
        return states_found

    return states(answer.casefold()) <= states(evidence)


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
    result = result.model_copy(
        update={"answer_text": cap_for_speech(result.answer_text)}
    )
    answer_audio = synthesize(result.answer_text)
    duration = _audio_duration(answer_audio)

    completed_web_calls = sum(
        step.tool == "web.search" and step.status == "completed"
        for step in result.steps
    )
    transcript_terms = set(re.findall(r"[a-z0-9]+", transcript.casefold()))
    canonical_product = next(
        (
            product
            for product in result.products
            if product.private.doc_id == CANONICAL_DOC_ID
        ),
        None,
    )
    canonical_live = canonical_product.live if canonical_product is not None else None
    has_price_conflict = bool(
        canonical_product
        and any(conflict.field == "price" for conflict in canonical_product.conflicts)
    )
    private_doc_ids = {
        citation.label for citation in result.citations if citation.kind == "private"
    }
    live_urls = {
        citation.url
        for citation in result.citations
        if citation.kind == "live" and citation.url
    }
    has_private_citation = CANONICAL_DOC_ID in private_doc_ids
    has_live_citation = bool(canonical_live and canonical_live.url in live_urls)
    answer_has_both_prices = bool(
        canonical_product
        and canonical_live
        and _number_is_mentioned(result.answer_text, canonical_product.private.price_low)
        and _number_is_mentioned(result.answer_text, canonical_live.price)
    )
    numeric_claims_grounded = bool(
        canonical_product
        and _numeric_claims_are_grounded(result.answer_text, canonical_product)
    )
    price_claims_grounded = bool(
        canonical_product
        and _price_claims_are_grounded(result.answer_text, canonical_product)
    )
    price_sources_grounded = bool(
        canonical_product
        and _price_sources_are_grounded(result.answer_text, canonical_product)
    )
    rating_claims_grounded = bool(
        canonical_product
        and _rating_claims_are_grounded(result.answer_text, canonical_product)
    )
    availability_claims_grounded = bool(
        canonical_product
        and _availability_claims_are_grounded(result.answer_text, canonical_product)
    )
    exact_spoken_text = cap_for_speech(result.answer_text) == result.answer_text

    checks = {
        "canonical_transcript": CANONICAL_TRANSCRIPT_TERMS <= transcript_terms,
        "web_search": completed_web_calls > 0,
        "canonical_product": canonical_product is not None,
        "live_serper_provenance": bool(
            canonical_live and canonical_live.origin == "live_serper"
        ),
        "price_conflict": has_price_conflict,
        "private_citation": has_private_citation,
        "live_citation": has_live_citation,
        "answer_has_both_prices": answer_has_both_prices,
        "numeric_claims_grounded": numeric_claims_grounded,
        "price_claims_grounded": price_claims_grounded,
        "price_sources_grounded": price_sources_grounded,
        "rating_claims_grounded": rating_claims_grounded,
        "availability_claims_grounded": availability_claims_grounded,
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
