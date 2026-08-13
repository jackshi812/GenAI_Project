"""Live MCP implementation of the ToolClient seam (Phase 2, Task 1).

One graph turn = one MCP server subprocess = one initialized ClientSession,
shared by the private call and every live call in that turn. This preserves
one rate-limit state per turn and avoids spawning a subprocess per product
(D-06). The session opens in ``__aenter__`` and closes once in ``__aexit__``;
``run_graph`` wraps the whole turn in this context.

Responses route through the same ``_decode`` helper as the fixture client:
same validation, same failure mode, same call site. A tool failure raises
``RuntimeError`` naming the tool; the Retriever catches it, keeps whatever
grounded private evidence remains, and records a truthful ``status: error``
step. Nothing here invents evidence.
"""

import json
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from contracts import RagResult, WebResult

from graph.tools import _decode, clean_filters

_REPO_ROOT = Path(__file__).resolve().parents[1]


class MCPTools:
    """ToolClient implementation backed by ``python -m mcp_server.server``."""

    def __init__(self):
        self._stack: AsyncExitStack | None = None
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "MCPTools":
        self._stack = AsyncExitStack()
        try:
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "mcp_server.server"],
                cwd=str(_REPO_ROOT),
                # Inherit the parent environment so SERPER_API_KEY, CHROMA_PATH
                # and the rate-limit settings reach the server process. Keys
                # are passed as env values only — never logged or printed.
                env=dict(os.environ),
            )
            read, write = await self._stack.enter_async_context(stdio_client(params))
            self._session = await self._stack.enter_async_context(
                ClientSession(read, write)
            )
            await self._session.initialize()
        except BaseException:
            await self._stack.aclose()
            self._stack = None
            self._session = None
            raise
        return self

    async def __aexit__(self, *exc) -> bool:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self._session = None
        return False

    async def rag_search(self, query: str, **filters) -> list[RagResult]:
        args = {"query": query, **clean_filters(filters)}
        payload = self._payload("rag.search", await self._call("rag.search", args))
        return _decode(payload, RagResult)

    async def web_search(self, query: str, num: int = 10) -> list[WebResult]:
        result = await self._call("web.search", {"query": query, "num": num})
        return _decode(self._payload("web.search", result), WebResult)

    async def _call(self, name: str, args: dict):
        if self._session is None:
            raise RuntimeError(
                f"{name} failed: MCPTools must be used inside its async context"
            )
        try:
            return await self._session.call_tool(name, args)
        except Exception as exc:
            raise RuntimeError(f"{name} failed: {exc}") from exc

    @staticmethod
    def _payload(name: str, result):
        """Extract and JSON-decode the single text content block; surface MCP
        error results as RuntimeError at this boundary."""
        texts = [
            block.text
            for block in (result.content or [])
            if getattr(block, "text", None)
        ]
        if getattr(result, "isError", False):
            detail = texts[0][:300] if texts else "unknown MCP tool error"
            raise RuntimeError(f"{name} failed: {detail}")
        if not texts:
            raise RuntimeError(f"{name} failed: MCP response had no text content")
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{name} failed: invalid JSON in MCP response") from exc
