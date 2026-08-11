"""The tool seam: one async interface, two implementations.

`FixtureTools` (graph/tools_stub.py) implements this against `fixtures.json`
today; Phase 2 adds `graph/tools_mcp.py` implementing the same interface
against Austin's MCP server (literal tool names `rag.search` / `web.search`)
— and no node changes.

The interface is async because the official MCP stdio client is async. The one
sync/async boundary in the whole system is `run_graph`.
"""

from typing import Protocol

from pydantic import TypeAdapter

from contracts import RagResult, WebResult

# Deterministic text rules live in graph.matching (stdlib-only); re-exported
# here because they belong conceptually to the tool seam.
from graph.matching import ALLOWED_RAG_FILTERS, clean_filters, eight_word_key  # noqa: F401


class ToolClient(Protocol):
    async def rag_search(self, query: str, **filters) -> list[RagResult]: ...

    async def web_search(self, query: str, num: int = 10) -> list[WebResult]: ...


_RAG_ADAPTER = TypeAdapter(list[RagResult])
_WEB_ADAPTER = TypeAdapter(list[WebResult])


def _decode(payload, model_cls) -> list:
    """Single shared decoding path for both implementations (stub feeds it
    fixture dicts; the MCP adapter feeds it json.loads(content_block.text)).
    Same validation, same failure mode, same call site."""
    if model_cls is RagResult:
        return _RAG_ADAPTER.validate_python(payload)
    if model_cls is WebResult:
        return _WEB_ADAPTER.validate_python(payload)
    raise TypeError(f"_decode does not handle {model_cls!r}")
