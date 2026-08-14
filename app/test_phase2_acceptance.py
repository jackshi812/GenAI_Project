"""Regression checks for the canonical Phase 2 acceptance chain."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.phase2_acceptance import CANONICAL_DOC_ID, run_once
from contracts import (
    AssistantResult,
    Citation,
    ComparisonProduct,
    Conflict,
    MatchInfo,
    RagResult,
    StepEvent,
    WebResult,
)


LIVE_URL = "https://www.ebay.com/itm/strongarm"


def _result(origin: str = "live_serper") -> AssistantResult:
    private = RagResult(
        sku="nerf",
        title="Nerf N Strike Elite Strongarm Blaster",
        price=13.99,
        rating=None,
        brand="Nerf",
        ingredients=None,
        doc_id=CANONICAL_DOC_ID,
        image_url="https://example.com/nerf.jpg",
        product_url="https://example.com/catalog",
        category="Toys",
        price_low=13.99,
        price_high=13.99,
        similarity=1.0,
        budget_fit="unknown",
    )
    live = WebResult(
        title="Nerf N Strike Elite Strongarm Blaster",
        url=LIVE_URL,
        snippet="eBay",
        price=10.95,
        availability="In stock",
        rating=None,
        origin=origin,
    )
    product = ComparisonProduct(
        private=private,
        live=live,
        conflicts=[
            Conflict(
                field="price",
                private_value=13.99,
                live_value=10.95,
                note="Price differs",
            )
        ],
        match=MatchInfo(similarity=1.0, verdict="same", reason="exact"),
    )
    return AssistantResult(
        transcript="Compare the Nerf Strongarm price.",
        plan="Compare private and live evidence.",
        answer_text="The catalog price is $13.99; live evidence shows $10.95.",
        products=[product],
        steps=[
            StepEvent(
                node="retriever",
                tool="web.search",
                started_at="2026-08-14T00:00:00Z",
                duration_ms=1,
                status="completed",
                detail="one result",
            )
        ],
        citations=[
            Citation(kind="private", label=CANONICAL_DOC_ID, url=None),
            Citation(kind="live", label="ebay.com", url=LIVE_URL),
        ],
    )


class Phase2AcceptanceTests(unittest.TestCase):
    def _run(self, transcript: str, result: AssistantResult) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            recording = Path(directory) / "question.mp3"
            recording.write_bytes(b"audio")
            with patch("app.phase2_acceptance.transcribe", return_value=transcript):
                with patch("app.phase2_acceptance.run_graph", return_value=result):
                    with patch("app.phase2_acceptance.synthesize", return_value=b"mp3"):
                        with patch("app.phase2_acceptance._audio_duration", return_value=9.0):
                            return run_once(recording, 1)

    def test_connected_canonical_evidence_chain_passes(self) -> None:
        outcome = self._run("Compare the Nerf Strongarm price.", _result())
        self.assertTrue(outcome["passed"])

    def test_wrong_transcript_and_recorded_fallback_fail(self) -> None:
        outcome = self._run("Compare a Lego suitcase.", _result("recorded_fixture"))
        self.assertFalse(outcome["passed"])
        self.assertFalse(outcome["checks"]["canonical_transcript"])
        self.assertFalse(outcome["checks"]["live_serper_provenance"])

    def test_invented_rating_is_rejected(self) -> None:
        result = _result().model_copy(
            update={
                "answer_text": (
                    "The catalog price is $13.99; live evidence shows $10.95. "
                    "Live rating is 5.0."
                )
            }
        )
        outcome = self._run("Compare the Nerf Strongarm price.", result)
        self.assertFalse(outcome["passed"])
        self.assertFalse(outcome["checks"]["numeric_claims_grounded"])

    def test_price_value_cannot_be_reused_as_a_rating(self) -> None:
        result = _result().model_copy(
            update={
                "answer_text": (
                    "The catalog price is $13.99; live evidence shows $10.95. "
                    "Live rating is 10.95."
                )
            }
        )
        outcome = self._run("Compare the Nerf Strongarm price.", result)
        self.assertFalse(outcome["passed"])
        self.assertFalse(outcome["checks"]["rating_claims_grounded"])

    def test_rating_was_form_cannot_reuse_a_price(self) -> None:
        result = _result().model_copy(
            update={
                "answer_text": (
                    "The catalog price is $13.99; live evidence shows $10.95. "
                    "The rating was 10.95."
                )
            }
        )
        outcome = self._run("Compare the Nerf Strongarm price.", result)
        self.assertFalse(outcome["passed"])
        self.assertFalse(outcome["checks"]["rating_claims_grounded"])

    def test_swapped_catalog_and_live_prices_are_rejected(self) -> None:
        result = _result().model_copy(
            update={
                "answer_text": (
                    "The catalog price is $10.95; live evidence shows $13.99."
                )
            }
        )
        outcome = self._run("Compare the Nerf Strongarm price.", result)
        self.assertFalse(outcome["passed"])
        self.assertFalse(outcome["checks"]["price_sources_grounded"])

    def test_contradictory_second_price_pair_is_rejected(self) -> None:
        result = _result().model_copy(
            update={
                "answer_text": (
                    "Catalog price $13.99; live price $10.95. "
                    "Catalog price $10.95; live price $13.99."
                )
            }
        )
        outcome = self._run("Compare the Nerf Strongarm price.", result)
        self.assertFalse(outcome["passed"])
        self.assertFalse(outcome["checks"]["price_sources_grounded"])

    def test_wrong_availability_is_rejected(self) -> None:
        result = _result().model_copy(
            update={
                "answer_text": (
                    "The catalog price is $13.99; live evidence shows $10.95 "
                    "and it is out of stock."
                )
            }
        )
        outcome = self._run("Compare the Nerf Strongarm price.", result)
        self.assertFalse(outcome["passed"])
        self.assertFalse(outcome["checks"]["availability_claims_grounded"])

    def test_sold_out_is_rejected_against_in_stock_evidence(self) -> None:
        result = _result().model_copy(
            update={
                "answer_text": (
                    "The catalog price is $13.99; live evidence shows $10.95 "
                    "and it is sold out."
                )
            }
        )
        outcome = self._run("Compare the Nerf Strongarm price.", result)
        self.assertFalse(outcome["passed"])
        self.assertFalse(outcome["checks"]["availability_claims_grounded"])

    def test_backordered_is_rejected_against_in_stock_evidence(self) -> None:
        result = _result().model_copy(
            update={
                "answer_text": (
                    "The catalog price is $13.99; live evidence shows $10.95 "
                    "and it is backordered."
                )
            }
        )
        outcome = self._run("Compare the Nerf Strongarm price.", result)
        self.assertFalse(outcome["passed"])
        self.assertFalse(outcome["checks"]["availability_claims_grounded"])

    def test_rating_came_in_at_cannot_reuse_a_price(self) -> None:
        result = _result().model_copy(
            update={
                "answer_text": (
                    "The catalog price is $13.99; live evidence shows $10.95. "
                    "The rating came in at 10.95."
                )
            }
        )
        outcome = self._run("Compare the Nerf Strongarm price.", result)
        self.assertFalse(outcome["passed"])
        self.assertFalse(outcome["checks"]["rating_claims_grounded"])

    def test_unrelated_number_and_price_substring_are_rejected(self) -> None:
        for answer in (
            "The catalog price is $13.99; live evidence shows $10.95 and 99 extras.",
            "The catalog price is $113.99; live evidence shows $10.95.",
        ):
            with self.subTest(answer=answer):
                result = _result().model_copy(update={"answer_text": answer})
                outcome = self._run("Compare the Nerf Strongarm price.", result)
                self.assertFalse(outcome["passed"])
                self.assertFalse(outcome["checks"]["numeric_claims_grounded"])


if __name__ == "__main__":
    unittest.main()
