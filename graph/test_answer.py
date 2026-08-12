"""Regression tests for Answerer/Critic citation completeness."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from contracts import ComparisonProduct, MatchInfo, RagResult, WebResult
from graph.answer import AnswerOutput, CriticOutput, answerer_node


LIVE_URL = "https://www.example.com/widget-alpha"


def _product() -> ComparisonProduct:
    private = RagResult(
        sku="widget-alpha",
        title="Widget Alpha",
        price=10.0,
        rating=None,
        brand="Widget",
        ingredients=None,
        doc_id="AMZ-WIDGET01",
        image_url="https://www.example.com/widget.jpg",
        product_url="https://www.example.com/catalog/widget-alpha",
        category="Test",
        price_low=10.0,
        price_high=10.0,
        similarity=0.9,
        budget_fit="unknown",
    )
    live = WebResult(
        title="Widget Alpha",
        url=LIVE_URL,
        snippet="Example retailer listing",
        price=21.95,
        availability="in stock",
        rating=4.5,
    )
    return ComparisonProduct(
        private=private,
        live=live,
        conflicts=[],
        match=MatchInfo(similarity=1.0, verdict="same", reason="Exact title match"),
    )


def _draft(*, include_live_url: bool) -> AnswerOutput:
    return AnswerOutput(
        answer_text="Widget Alpha has a live price of $21.95; details are on screen.",
        cited_doc_ids=["AMZ-WIDGET01"],
        cited_urls=[LIVE_URL] if include_live_url else [],
    )


class CitationCompletenessTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_live_url_triggers_retry_and_fixed_citation_is_returned(self) -> None:
        answer_call = AsyncMock(side_effect=[_draft(include_live_url=False), _draft(include_live_url=True)])
        critic_call = AsyncMock(
            side_effect=[
                CriticOutput(
                    grounded=True,
                    citations_complete=False,
                    ungrounded_claims=[],
                    missing_citations=[LIVE_URL],
                ),
                CriticOutput(
                    grounded=True,
                    citations_complete=True,
                    ungrounded_claims=[],
                    missing_citations=[],
                ),
            ]
        )

        with patch("graph.answer._answer_call", answer_call), patch(
            "graph.answer._critic_call", critic_call
        ):
            result = await answerer_node(
                {
                    "products": [_product()],
                    "transcript": "What is its live price?",
                    "plan": "Use private and live evidence.",
                    "use_private": True,
                }
            )

        self.assertEqual(answer_call.await_count, 2)
        self.assertIn(LIVE_URL, [citation.url for citation in result["citations"]])
        self.assertIn("critic rejected first draft", result["steps"][0].detail)

    async def test_repeated_missing_live_url_degrades_to_deterministically_cited_answer(self) -> None:
        answer_call = AsyncMock(side_effect=[_draft(include_live_url=False), _draft(include_live_url=False)])
        incomplete = CriticOutput(
            grounded=True,
            citations_complete=False,
            ungrounded_claims=[],
            missing_citations=[LIVE_URL],
        )
        critic_call = AsyncMock(side_effect=[incomplete, incomplete])

        with patch("graph.answer._answer_call", answer_call), patch(
            "graph.answer._critic_call", critic_call
        ):
            result = await answerer_node(
                {
                    "products": [_product()],
                    "transcript": "What is its live price?",
                    "plan": "Use private and live evidence.",
                    "use_private": True,
                }
            )

        citations = {(citation.kind, citation.url or citation.label) for citation in result["citations"]}
        self.assertIn(("private", "AMZ-WIDGET01"), citations)
        self.assertIn(("live", LIVE_URL), citations)
        self.assertIn("degraded to evidence-only answer", result["steps"][0].detail)


if __name__ == "__main__":
    unittest.main()
