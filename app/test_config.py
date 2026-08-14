"""Regression checks for user-visible evidence-source labels."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import live_evidence_notice, source_mode_label
from contracts import (
    AssistantResult,
    ComparisonProduct,
    MatchInfo,
    RagResult,
    StepEvent,
    WebResult,
)


class SourceModeLabelTests(unittest.TestCase):
    def test_fixture_mode_is_explicitly_recorded(self) -> None:
        with patch.dict(os.environ, {"TOOL_MODE": "fixture"}, clear=True):
            self.assertEqual(source_mode_label(), "Fixture graph · Recorded data")

    def test_live_mcp_with_key_is_live_serper(self) -> None:
        with patch.dict(
            os.environ,
            {"TOOL_MODE": "live", "SERPER_API_KEY": "configured"},
            clear=True,
        ):
            self.assertEqual(source_mode_label(), "Live MCP · Live Serper")

    def test_live_mcp_without_key_is_recorded_serper(self) -> None:
        with patch.dict(os.environ, {"TOOL_MODE": "live"}, clear=True):
            self.assertEqual(source_mode_label(), "Live MCP · Recorded Serper")

    @staticmethod
    def _result_with_origin(origin: str) -> AssistantResult:
        private = RagResult(
            sku="sku",
            title="Widget",
            price=10.0,
            rating=None,
            brand=None,
            ingredients=None,
            doc_id="DOC-1",
            image_url="https://example.com/image.jpg",
            product_url="https://example.com/product",
            category=None,
            price_low=10.0,
            price_high=10.0,
            similarity=1.0,
            budget_fit="unknown",
        )
        live = WebResult(
            title="Widget",
            url="https://example.com/live",
            snippet="evidence",
            price=9.0,
            availability=None,
            rating=None,
            origin=origin,
        )
        product = ComparisonProduct(
            private=private,
            live=live,
            conflicts=[],
            match=MatchInfo(similarity=1.0, verdict="same", reason="exact"),
        )
        return AssistantResult(
            transcript="query",
            plan=None,
            answer_text="answer",
            products=[product],
            steps=[],
            citations=[],
        )

    def test_result_provenance_overrides_credential_presence(self) -> None:
        recorded = self._result_with_origin("recorded_fixture")
        live = self._result_with_origin("live_serper")
        with patch.dict(
            os.environ,
            {"TOOL_MODE": "live", "SERPER_API_KEY": "configured"},
            clear=True,
        ):
            self.assertEqual(
                source_mode_label(recorded), "Live MCP · Recorded Serper"
            )
            self.assertEqual(source_mode_label(live), "Live MCP · Live Serper")


class LiveEvidenceNoticeTests(unittest.TestCase):
    @staticmethod
    def _result(*steps: StepEvent) -> AssistantResult:
        return AssistantResult(
            transcript="query",
            plan=None,
            answer_text="answer",
            products=[],
            steps=list(steps),
            citations=[],
        )

    @staticmethod
    def _web_step(status: str) -> StepEvent:
        return StepEvent(
            node="retriever",
            tool="web.search",
            started_at="2026-08-14T00:00:00Z",
            duration_ms=1,
            status=status,
            detail="test",
        )

    def test_no_lookup_is_distinct_from_no_match(self) -> None:
        self.assertEqual(
            live_evidence_notice(self._result()),
            ("caption", "Live lookup was not requested for this result."),
        )
        self.assertEqual(
            live_evidence_notice(self._result(self._web_step("completed"))),
            ("warning", "Live lookup completed, but no product match was confirmed."),
        )

    def test_failed_lookup_is_a_warning(self) -> None:
        kind, message = live_evidence_notice(self._result(self._web_step("error")))
        self.assertEqual(kind, "warning")
        self.assertIn("failed", message)


if __name__ == "__main__":
    unittest.main()
