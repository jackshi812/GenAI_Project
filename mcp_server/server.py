"""Low-level stdio MCP server exposing exactly rag.search and web.search."""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mcp.server.stdio
from mcp import types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from catalog.search import search
from mcp_server.web_search import web_search

LOG_PATH = Path(__file__).resolve().parent / "logs" / "mcp.jsonl"
server = Server("product-discovery-tools")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize(item)
            for key, item in value.items()
            if not any(marker in key.lower() for marker in ("key", "token", "secret"))
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _write_log(payload: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="rag.search",
            description=(
                "Search the private Amazon Product Dataset 2020 catalog with "
                "semantic retrieval and metadata filters. The private corpus "
                "contains no ratings."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "price_max": {"type": "number"},
                    "price_min": {"type": "number"},
                    "category": {"type": "string"},
                    "brand": {"type": "string"},
                    "k": {"type": "integer", "minimum": 1, "maximum": 50, "default": 6},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="web.search",
            description=(
                "Search current shopping evidence through Serper, or replay an "
                "exact recorded Serper response when no API key is configured."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "num": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 10,
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    started = time.perf_counter()
    safe_arguments = _sanitize(arguments or {})
    _write_log(
        {
            "timestamp": _timestamp(),
            "direction": "request",
            "tool": name,
            "arguments": safe_arguments,
        }
    )
    try:
        if name == "rag.search":
            results = await asyncio.to_thread(
                search,
                query=arguments["query"],
                price_max=arguments.get("price_max"),
                price_min=arguments.get("price_min"),
                category=arguments.get("category"),
                brand=arguments.get("brand"),
                k=arguments.get("k", 6),
            )
        elif name == "web.search":
            results = await asyncio.to_thread(
                web_search,
                query=arguments["query"],
                num=arguments.get("num", 10),
            )
        else:
            raise ValueError(f"Unknown tool: {name}")
    except Exception as exc:
        _write_log(
            {
                "timestamp": _timestamp(),
                "direction": "response",
                "tool": name,
                "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
                "result_count": 0,
                "error": type(exc).__name__,
            }
        )
        raise

    response_log: dict[str, Any] = {
        "timestamp": _timestamp(),
        "direction": "response",
        "tool": name,
        "elapsed_ms": round((time.perf_counter() - started) * 1_000, 3),
        "result_count": len(results),
    }
    if name == "web.search":
        response_log["source_urls"] = [item["url"] for item in results]
    _write_log(response_log)
    return [
        types.TextContent(
            type="text",
            text=json.dumps(results, ensure_ascii=False),
        )
    ]


async def run() -> None:
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="product-discovery-tools",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(run())
