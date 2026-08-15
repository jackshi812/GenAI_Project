"""Graph assembly and the public entry point.

Jack's app calls exactly one function:

    run_graph(transcript: str) -> AssistantResult

The sync/async bridge wraps the complete graph turn — the app receives one
completed result, never a stream or raw LangGraph state (D-14). Phase 2
changes how the tool client is selected inside this module, not the call
signature.
"""

import asyncio
import os

from langgraph.graph import END, START, StateGraph

from contracts import AssistantResult

from graph.answer import answerer_node
from graph.interactive import (
    interactive_answerer_node,
    interactive_planner_node,
    interactive_router_node,
)
from graph.nodes import planner_node, router_node
from graph.retriever import make_retriever_node
from graph.state import GraphState
from graph.tools_stub import FixtureTools

TOOL_MODES = ("live", "fixture")
GRAPH_MODES = ("interactive", "llm")


def build_graph(tools, *, mode: str | None = None):
    """Assemble router -> planner -> retriever -> answerer around an injected
    ToolClient. Compiled graph; nodes are async."""
    selected_mode = (mode or os.getenv("GRAPH_MODE", "interactive")).strip().lower()
    if selected_mode not in GRAPH_MODES:
        raise ValueError(
            f"Unsupported GRAPH_MODE={selected_mode!r}; supported values are "
            f"{GRAPH_MODES[0]!r} and {GRAPH_MODES[1]!r}."
        )
    interactive = selected_mode == "interactive"
    g = StateGraph(GraphState)
    g.add_node("router", interactive_router_node if interactive else router_node)
    g.add_node("planner", interactive_planner_node if interactive else planner_node)
    g.add_node("retriever", make_retriever_node(tools, interactive=interactive))
    g.add_node(
        "answerer",
        interactive_answerer_node if interactive else answerer_node,
    )
    g.add_edge(START, "router")
    g.add_edge("router", "planner")
    g.add_edge("planner", "retriever")
    g.add_edge("retriever", "answerer")
    g.add_edge("answerer", END)
    return g.compile()


def _select_tools():
    """Choose the tool client from TOOL_MODE (Phase 2, Task 1).

    ``live`` (default) starts one MCP server session for the whole turn via
    ``MCPTools``; ``fixture`` replays recorded data through ``FixtureTools``
    and stays available as the explicit recorded-tool fallback.
    """
    mode = os.getenv("TOOL_MODE", "live").strip().lower()
    if mode == "live":
        from graph.tools_mcp import MCPTools  # imported lazily: needs mcp SDK

        return MCPTools()
    if mode == "fixture":
        return FixtureTools()
    raise ValueError(
        f"Unsupported TOOL_MODE={mode!r}; supported values are "
        f"{TOOL_MODES[0]!r} and {TOOL_MODES[1]!r}."
    )


async def _run(
    transcript: str,
    tools=None,
    *,
    graph_mode: str | None = None,
) -> AssistantResult:
    """One async runner for the whole turn. The single sync/async boundary is
    run_graph; nothing else calls asyncio.run. One call means one tool-client
    lifecycle — in live mode, one MCP server process and one session serving
    both rag.search and every web.search call of the turn."""
    if tools is None:
        tools = _select_tools()
    async with tools:
        graph = build_graph(tools, mode=graph_mode)
        final = await graph.ainvoke({"transcript": transcript, "steps": []})
    return _to_result(final)


def run_graph(transcript: str) -> AssistantResult:
    """UI-facing synchronous wrapper. Tool selection follows TOOL_MODE;
    the signature is unchanged from Phase 1."""
    return asyncio.run(_run(transcript))


def _to_result(state: dict) -> AssistantResult:
    # Exactly the six contract fields (strict model, extra="forbid"); the
    # extracted intent stays graph-internal and reaches the UI via step detail.
    return AssistantResult(
        transcript=state.get("transcript", ""),
        plan=state.get("plan"),
        answer_text=state.get("answer_text", ""),
        products=state.get("products", []),
        steps=state.get("steps", []),
        citations=state.get("citations", []),
    )


if __name__ == "__main__":
    result = run_graph("Find me a 500 piece jigsaw puzzle under twenty dollars.")
    for s in result.steps:
        print(f"[{s.status:>9}] {s.node:<10} tool={s.tool or '-':<12} {s.duration_ms}ms  {s.detail}")
    print(f"\nanswer: {result.answer_text}")
