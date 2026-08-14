"""Tests for grounded follow-up speech in the LiveKit pipeline."""

from __future__ import annotations

import unittest

from contracts import (
    AssistantResult,
    ComparisonProduct,
    Conflict,
    MatchInfo,
    RagResult,
    StepEvent,
    WebResult,
)
from voice.livekit_agent import compose_live_followup


def _private() -> RagResult:
    return RagResult(
        sku="nerf",
        title="Nerf Strongarm",
        price=13.99,
        rating=None,
        brand="Nerf",
        ingredients=None,
        doc_id="AMZ-NERF",
        image_url="https://example.com/image.jpg",
        product_url="https://example.com/product",
        category="Toys & Games",
        price_low=13.99,
        price_high=13.99,
        similarity=1.0,
        budget_fit="unknown",
    )


def _result(product: ComparisonProduct, *steps: StepEvent) -> AssistantResult:
    return AssistantResult(
        transcript="current Nerf price",
        plan="compare",
        answer_text="unused",
        products=[product],
        steps=list(steps),
        citations=[],
    )


class LiveFollowupTests(unittest.TestCase):
    def test_live_price_followup_preserves_provenance(self) -> None:
        live = WebResult(
            title="Nerf Strongarm",
            url="https://example.com/live",
            snippet="evidence",
            price=21.95,
            availability=None,
            rating=None,
            origin="live_serper",
        )
        product = ComparisonProduct(
            private=_private(),
            live=live,
            conflicts=[
                Conflict(
                    field="price",
                    private_value=13.99,
                    live_value=21.95,
                    note="different prices",
                )
            ],
            match=MatchInfo(similarity=1.0, verdict="same", reason="exact"),
        )
        text = compose_live_followup(_result(product))
        self.assertIn("current matched listing", text)
        self.assertIn("$21.95", text)
        self.assertIn("$13.99", text)

    def test_recorded_result_is_not_called_current(self) -> None:
        live = WebResult(
            title="Nerf Strongarm",
            url="https://example.com/recorded",
            snippet="evidence",
            price=21.95,
            availability=None,
            rating=None,
            origin="recorded_fixture",
        )
        product = ComparisonProduct(
            private=_private(),
            live=live,
            conflicts=[],
            match=MatchInfo(similarity=1.0, verdict="same", reason="exact"),
        )
        text = compose_live_followup(_result(product))
        self.assertIn("recorded web result", text)
        self.assertNotIn("current matched", text)

    def test_completed_search_without_match_is_honest(self) -> None:
        product = ComparisonProduct(
            private=_private(), live=None, conflicts=[], match=None
        )
        step = StepEvent(
            node="retriever",
            tool="web.search",
            started_at="2026-08-14T00:00:00Z",
            duration_ms=10,
            status="completed",
            detail="0 results",
        )
        text = compose_live_followup(_result(product, step))
        self.assertIn("couldn’t confirm an exact online match", text)


if __name__ == "__main__":
    unittest.main()
