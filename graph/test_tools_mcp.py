"""Unit tests for MCPTools and TOOL_MODE selection — no real MCP server, no
network, no API key. The protocol content shapes mirror mcp_server/server.py:
one TextContent block holding one JSON array.

Run:  python -m unittest -v graph.test_tools_mcp
"""

import asyncio
import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from graph.tools_mcp import MCPTools


def _text_result(payload, is_error=False):
    block = SimpleNamespace(type="text", text=json.dumps(payload) if not is_error else payload)
    return SimpleNamespace(content=[block], isError=is_error)


RAG_ROW = {
    "sku": "s1",
    "title": "Widget Alpha 500 Piece Puzzle",
    "price": 10.99,
    "rating": None,
    "brand": "Widget",
    "ingredients": None,
    "doc_id": "AMZ-TEST0001",
    "image_url": "https://example.com/i.jpg",
    "product_url": "https://example.com/p",
    "category": "Toys & Games",
    "price_low": 10.99,
    "price_high": 10.99,
    "similarity": 0.9,
    "budget_fit": "within",
}

WEB_ROW = {
    "title": "Widget Alpha 500 Piece Puzzle",
    "url": "https://example.com/live",
    "snippet": "listing",
    "price": 12.5,
    "availability": "In stock",
    "rating": 4.5,
}


class FakeSession:
    """Records call_tool invocations and replays canned MCP-shaped results."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        result = self.results[name]
        if isinstance(result, Exception):
            raise result
        return result


def _client(results):
    tools = MCPTools()
    tools._session = FakeSession(results)
    return tools


class MCPToolsTests(unittest.TestCase):
    def test_rag_search_decodes_and_forwards_only_allowed_filters(self):
        tools = _client({"rag.search": _text_result([RAG_ROW])})
        out = asyncio.run(
            tools.rag_search(
                "widget puzzle", price_max=20.0, k=5, bogus="dropme", brand=None
            )
        )
        self.assertEqual([r.doc_id for r in out], ["AMZ-TEST0001"])
        name, args = tools._session.calls[0]
        self.assertEqual(name, "rag.search")
        self.assertEqual(args, {"query": "widget puzzle", "price_max": 20.0, "k": 5})

    def test_web_search_decodes_webresults(self):
        tools = _client({"web.search": _text_result([WEB_ROW])})
        out = asyncio.run(tools.web_search("widget puzzle", num=5))
        self.assertEqual(out[0].url, "https://example.com/live")
        self.assertEqual(tools._session.calls[0][1], {"query": "widget puzzle", "num": 5})

    def test_error_result_raises_runtimeerror_naming_tool(self):
        tools = _client({"web.search": _text_result("Serper exploded", is_error=True)})
        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(tools.web_search("widget"))
        self.assertIn("web.search failed", str(ctx.exception))

    def test_transport_exception_wrapped_as_runtimeerror(self):
        tools = _client({"rag.search": ConnectionError("pipe closed")})
        with self.assertRaises(RuntimeError) as ctx:
            asyncio.run(tools.rag_search("widget"))
        self.assertIn("rag.search failed", str(ctx.exception))

    def test_use_outside_context_raises(self):
        tools = MCPTools()
        with self.assertRaises(RuntimeError):
            asyncio.run(tools.rag_search("widget"))

    def test_invalid_json_payload_raises(self):
        block = SimpleNamespace(type="text", text="not json")
        result = SimpleNamespace(content=[block], isError=False)
        tools = _client({"rag.search": result})
        with self.assertRaises(RuntimeError):
            asyncio.run(tools.rag_search("widget"))


class ToolModeSelectionTests(unittest.TestCase):
    def test_fixture_mode_selects_fixture_tools(self):
        from graph.build import _select_tools
        from graph.tools_stub import FixtureTools

        with patch.dict(os.environ, {"TOOL_MODE": "fixture"}):
            self.assertIsInstance(_select_tools(), FixtureTools)

    def test_default_and_live_mode_select_mcp_tools(self):
        from graph.build import _select_tools

        with patch.dict(os.environ, {"TOOL_MODE": "live"}):
            self.assertIsInstance(_select_tools(), MCPTools)
        env = {k: v for k, v in os.environ.items() if k != "TOOL_MODE"}
        with patch.dict(os.environ, env, clear=True):
            self.assertIsInstance(_select_tools(), MCPTools)

    def test_invalid_mode_raises_valueerror(self):
        from graph.build import _select_tools

        with patch.dict(os.environ, {"TOOL_MODE": "banana"}):
            with self.assertRaises(ValueError):
                _select_tools()


if __name__ == "__main__":
    unittest.main()
