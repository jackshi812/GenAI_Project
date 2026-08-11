"""Launch the stdio MCP server and exercise discovery plus both tools."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from catalog.search import search

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PATH = REPO_ROOT / "catalog" / "canonical_queries.json"
LOG_PATH = Path(__file__).resolve().parent / "logs" / "mcp.jsonl"


def _decode(result: Any) -> list[dict[str, Any]]:
    if result.isError:
        raise RuntimeError(result.content)
    return json.loads(result.content[0].text)


async def main() -> None:
    canonical = json.loads(CANONICAL_PATH.read_text(encoding="utf-8"))
    rag_case = canonical[0]
    conflict_case = canonical[2]
    conflict_results = search(
        conflict_case["semantic_query"],
        **{**conflict_case["filters"], "k": 5},
    )
    expected = set(conflict_case["expected_doc_ids"])
    conflict_title = next(
        item["title"] for item in conflict_results if item["doc_id"] in expected
    )

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(REPO_ROOT),
        env=dict(os.environ),
    )
    async with (
        stdio_client(params) as (read_stream, write_stream),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        discovery = await session.list_tools()
        print("## tools/list")
        print(
            json.dumps(
                [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema,
                    }
                    for tool in discovery.tools
                ],
                indent=2,
            )
        )
        assert [tool.name for tool in discovery.tools] == ["rag.search", "web.search"]

        rag_arguments = {"query": rag_case["semantic_query"], **rag_case["filters"]}
        rag_result = _decode(await session.call_tool("rag.search", rag_arguments))
        print("\n## rag.search")
        print(json.dumps(rag_result, indent=2, ensure_ascii=False))

        started = time.perf_counter()
        first_web = _decode(
            await session.call_tool("web.search", {"query": conflict_title, "num": 10})
        )
        first_elapsed = time.perf_counter() - started
        print(f"\n## web.search first call ({first_elapsed:.4f}s)")
        print(json.dumps(first_web, indent=2, ensure_ascii=False))

        started = time.perf_counter()
        second_web = _decode(
            await session.call_tool("web.search", {"query": conflict_title, "num": 10})
        )
        second_elapsed = time.perf_counter() - started
        print(f"\n## web.search cached call ({second_elapsed:.4f}s)")
        print(json.dumps(second_web, indent=2, ensure_ascii=False))
        assert first_web == second_web

    print("\n## last six MCP log lines")
    if LOG_PATH.exists():
        lines = LOG_PATH.read_text(encoding="utf-8").splitlines()
        print("\n".join(lines[-6:]))
    else:
        print("log file not created")


if __name__ == "__main__":
    asyncio.run(main())
