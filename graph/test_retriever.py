"""Focused checks for shortlist-wide deterministic matching guards."""

import unittest
from unittest.mock import patch

from contracts import RagResult, WebResult
from graph.retriever import MatchDecision, _reconcile_one


def _private(title: str) -> RagResult:
    return RagResult(
        sku="test-sku",
        title=title,
        price=10.0,
        rating=None,
        brand="Widget",
        ingredients=None,
        doc_id="TEST-DOC",
        image_url="https://example.com/image",
        product_url="https://example.com/product",
        category="Test",
        price_low=10.0,
        price_high=10.0,
        similarity=1.0,
        budget_fit="unknown",
    )


def _live(title: str) -> WebResult:
    return WebResult(
        title=title,
        url="https://example.com/live",
        snippet="",
        price=10.0,
        availability=None,
        rating=None,
    )


class ReconcileGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_conflicting_top_hit_does_not_hide_valid_lower_hit(self):
        private = _private("Widget Alpha Pro 2 pack red")
        conflicting = _live("Widget Alpha Pro 4 pack red")
        valid = _live("Widget Alpha Pro 2 pack red edition")

        result = await _reconcile_one(private, [conflicting, valid])

        self.assertIsNotNone(result.live)
        self.assertEqual(result.live.title, valid.title)
        self.assertEqual(result.match.verdict, "same")

    async def test_conflicting_candidates_are_not_sent_to_llm(self):
        private = _private("Widget Alpha Pro 2 pack red")
        ambiguous = _live("Widget Alpha Pro")
        conflicting = _live("Widget Alpha Pro 4 pack blue")

        async def confirm(_, candidates):
            self.assertEqual([candidate.title for candidate in candidates], [ambiguous.title])
            return MatchDecision(candidate_index=0, verdict="same", reason="Shortened title")

        with patch("graph.retriever._llm_confirm", confirm):
            result = await _reconcile_one(private, [ambiguous, conflicting])

        self.assertIsNotNone(result.live)
        self.assertEqual(result.live.title, ambiguous.title)

    async def test_llm_selection_is_checked_again_before_acceptance(self):
        private = _private("Widget Alpha Pro 2 pack red")
        ambiguous = _live("Widget Alpha Pro")

        async def mutate_then_confirm(_, candidates):
            candidates[0].title = "Widget Alpha Pro 4 pack blue"
            return MatchDecision(candidate_index=0, verdict="same", reason="Incorrect decision")

        with patch("graph.retriever._llm_confirm", mutate_then_confirm):
            result = await _reconcile_one(private, [ambiguous])

        self.assertIsNone(result.live)
        self.assertEqual(result.match.verdict, "different")
        self.assertIn("deterministic variant guard", result.match.reason)


if __name__ == "__main__":
    unittest.main()
