"""Focused checks for shortlist-wide deterministic matching guards."""

import unittest
from unittest.mock import patch

from contracts import RagResult, ShoppingContext, WebResult
from graph.retriever import MatchDecision, _reconcile_one, make_retriever_node


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


class _RetrieverTools:
    def __init__(
        self,
        rag_results: list[RagResult],
        web_results: list[WebResult],
    ) -> None:
        self.rag_results = rag_results
        self.web_results = web_results
        self.rag_calls: list[tuple[str, dict]] = []
        self.web_calls: list[tuple[str, int]] = []

    async def rag_search(self, query: str, **filters):
        self.rag_calls.append((query, filters))
        return self.rag_results

    async def web_search(self, query: str, num: int = 10):
        self.web_calls.append((query, num))
        return self.web_results


class RetrieverResultLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_twelve_catalog_candidates_return_first_six_with_six_live_lookups(self):
        candidates = [
            _private(f"Widget Candidate {index}").model_copy(
                update={
                    "sku": f"widget-{index}",
                    "doc_id": f"WIDGET-{index}",
                }
            )
            for index in range(12)
        ]
        tools = _RetrieverTools(candidates, [])

        result = await make_retriever_node(tools)(
            {
                "use_private": True,
                "use_live": True,
                "semantic_query": "widget",
                "filters": {"k": 12},
            }
        )

        self.assertEqual(
            [product.private.doc_id for product in result["products"]],
            [f"WIDGET-{index}" for index in range(6)],
        )
        self.assertEqual(tools.rag_calls, [("widget", {"k": 12})])
        self.assertEqual(len(tools.web_calls), 6)

    async def test_private_exclusion_is_applied_before_cap_and_live_lookups(self):
        black = _private("Black Travel Backpack").model_copy(
            update={"sku": "black-backpack", "doc_id": "BLACK-BACKPACK"}
        )
        non_black = [
            _private(f"Pink Canvas Travel Backpack {index}").model_copy(
                update={
                    "sku": f"pink-backpack-{index}",
                    "doc_id": f"PINK-BACKPACK-{index}",
                }
            )
            for index in range(6)
        ]
        tools = _RetrieverTools([black, *non_black], [])

        result = await make_retriever_node(tools)(
            {
                "use_private": True,
                "use_live": True,
                "semantic_query": "backpack",
                "filters": {"k": 12},
                "shopping_context": ShoppingContext(
                    product_query="backpack",
                    excluded=["black"],
                    resolved_query="backpack",
                ),
            }
        )

        self.assertEqual(
            [product.private.doc_id for product in result["products"]],
            [f"PINK-BACKPACK-{index}" for index in range(6)],
        )
        self.assertEqual(
            [product.doc_id for product in result["rag_results"]],
            [f"PINK-BACKPACK-{index}" for index in range(6)],
        )
        self.assertEqual(len(tools.web_calls), 6)

    async def test_direct_web_fallback_requests_twelve_and_returns_first_six(self):
        hits = [
            _live(f"Web Widget {index}").model_copy(
                update={"url": f"https://example.com/web-{index}"}
            )
            for index in range(12)
        ]
        tools = _RetrieverTools([], hits)

        result = await make_retriever_node(tools)(
            {
                "use_private": True,
                "use_live": False,
                "semantic_query": "web widget",
                "filters": {"k": 12},
            }
        )

        self.assertEqual(tools.web_calls, [("web widget", 12)])
        self.assertEqual(
            [product.live.url for product in result["products"]],
            [f"https://example.com/web-{index}" for index in range(6)],
        )

    async def test_direct_web_fallback_filters_exclusion_before_six_item_cap(self):
        black = _live("Black Travel Backpack").model_copy(
            update={
                "url": "https://example.com/black-backpack",
                "snippet": "Compact black backpack",
            }
        )
        non_black = [
            _live(f"Pink Canvas Travel Backpack {index}").model_copy(
                update={"url": f"https://example.com/pink-backpack-{index}"}
            )
            for index in range(6)
        ]
        tools = _RetrieverTools([], [black, *non_black])

        result = await make_retriever_node(tools)(
            {
                "use_private": True,
                "use_live": False,
                "semantic_query": "backpack",
                "filters": {"k": 12},
                "shopping_context": ShoppingContext(
                    product_query="backpack",
                    excluded=["black"],
                    resolved_query="backpack",
                ),
            }
        )

        expected_urls = [
            f"https://example.com/pink-backpack-{index}" for index in range(6)
        ]
        self.assertEqual(
            [product.live.url for product in result["products"]],
            expected_urls,
        )
        self.assertEqual(
            [product.url for product in result["web_results"]],
            expected_urls,
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
