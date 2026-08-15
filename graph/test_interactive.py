"""Checks for the low-latency LangGraph execution mode."""

from __future__ import annotations

import unittest

from contracts import RagResult, WebResult
from graph.build import _run, build_graph


def _catalog_product() -> RagResult:
    return RagResult(
        sku="pantry-box",
        title="Fresh Grocery Pantry Box",
        price=18.0,
        rating=None,
        brand="Fresh",
        ingredients=None,
        doc_id="CAT-PANTRY",
        image_url="https://example.com/pantry.jpg",
        product_url="https://example.com/pantry",
        category="Grocery & Gourmet Food",
        price_low=18.0,
        price_high=18.0,
        similarity=0.9,
        budget_fit="within",
    )


def _live_product() -> WebResult:
    return WebResult(
        title="Pokemon Trading Card Booster Pack",
        url="https://www.walmart.com/ip/pokemon-booster",
        snippet="Walmart",
        price=14.99,
        availability="Delivery",
        image_url="https://example.com/pokemon.jpg",
        rating=4.7,
        origin="live_serper",
    )


class _Tools:
    def __init__(self, rag_results: list[RagResult] | None = None) -> None:
        self.rag_results = rag_results or []
        self.rag_calls = []
        self.web_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def rag_search(self, query: str, **filters):
        self.rag_calls.append((query, filters))
        return self.rag_results

    async def web_search(self, query: str, num: int = 10):
        self.web_calls.append((query, num))
        return [_live_product()]


class InteractiveGraphTests(unittest.IsolatedAsyncioTestCase):
    async def test_named_product_uses_one_web_call_and_no_llm_wait(self) -> None:
        tools = _Tools()

        result = await _run(
            "Find me Pokemon cards under $25",
            tools,
            graph_mode="interactive",
        )

        self.assertEqual(len(tools.rag_calls), 1)
        self.assertEqual(len(tools.web_calls), 1)
        self.assertEqual(result.products[0].live.title, _live_product().title)
        self.assertIn(_live_product().url, [item.url for item in result.citations])
        self.assertEqual(
            [step.node for step in result.steps if step.node in {"router", "planner", "answerer"}],
            ["router", "planner", "answerer"],
        )
        self.assertIn("evidence-only", result.steps[-1].detail)

    async def test_broad_catalog_request_skips_web_when_rag_matches(self) -> None:
        tools = _Tools([_catalog_product()])

        result = await _run(
            "What groceries can I buy under $20?",
            tools,
            graph_mode="interactive",
        )

        self.assertEqual(len(tools.web_calls), 0)
        self.assertEqual(result.products[0].private.doc_id, "CAT-PANTRY")
        self.assertEqual(
            tools.rag_calls[0][1]["category"], "Grocery & Gourmet Food"
        )
        self.assertEqual(tools.rag_calls[0][1]["price_max"], 20.0)

    async def test_conversation_skips_product_tools(self) -> None:
        tools = _Tools()

        result = await _run(
            "How are you doing today?",
            tools,
            graph_mode="interactive",
        )

        self.assertEqual(tools.rag_calls, [])
        self.assertEqual(tools.web_calls, [])
        self.assertIn("thanks for asking", result.answer_text)

    async def test_greeting_before_grocery_request_still_uses_product_tools(self) -> None:
        tools = _Tools()

        result = await _run(
            "Hello, I need vegetables like broccoli and lettuce",
            tools,
            graph_mode="interactive",
        )

        self.assertEqual(tools.rag_calls[0][0], "vegetables broccoli lettuce")
        self.assertEqual(
            tools.rag_calls[0][1]["category"], "Grocery & Gourmet Food"
        )
        self.assertEqual(len(tools.web_calls), 1)
        self.assertNotIn("thanks for asking", result.answer_text)

    async def test_hazardous_mixing_request_stops_before_tools(self) -> None:
        tools = _Tools()

        result = await _run(
            "Can I mix bleach and ammonia for a stronger cleaner?",
            tools,
            graph_mode="interactive",
        )

        self.assertEqual(tools.rag_calls, [])
        self.assertEqual(tools.web_calls, [])
        self.assertIn("hazardous chemical mixing", result.answer_text)

    def test_unknown_graph_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_graph(_Tools(), mode="slow-and-mysterious")


if __name__ == "__main__":
    unittest.main()
