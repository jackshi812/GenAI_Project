"""Graph assembly and the public entry point.

Jack's app calls exactly one function:

    run_graph(transcript: str) -> AssistantResult

The sync/async bridge wraps the complete graph turn — the app receives one
completed result, never a stream or raw LangGraph state (D-14). Phase 2
changes how the tool client is selected inside this module, not the call
signature.
"""

import asyncio

from langgraph.graph import END, START, StateGraph

from contracts import AssistantResult

from graph.answer import answerer_node
from graph.nodes import planner_node, router_node
from graph.retriever import make_retriever_node
from graph.state import GraphState
from graph.tools_stub import FixtureTools


def build_graph(tools):
    """Assemble router -> planner -> retriever -> answerer around an injected
    ToolClient. Compiled graph; nodes are async."""
    g = StateGraph(GraphState)
    g.add_node("router", router_node)
    g.add_node("planner", planner_node)
    g.add_node("retriever", make_retriever_node(tools))
    g.add_node("answerer", answerer_node)
    g.add_edge(START, "router")
    g.add_edge("router", "planner")
    g.add_edge("planner", "retriever")
    g.add_edge("retriever", "answerer")
    g.add_edge("answerer", END)
    return g.compile()


async def _run(transcript: str, tools=None) -> AssistantResult:
    """One async runner for the whole turn. The single sync/async boundary is
    run_graph; nothing else calls asyncio.run."""
    if tools is None:
        tools = FixtureTools()
    async with tools:
        graph = build_graph(tools)
        final = await graph.ainvoke({"transcript": transcript, "steps": []})
    return _to_result(final)


def run_graph(transcript: str) -> AssistantResult:
    """UI-facing synchronous wrapper (Phase 1: fixture tools)."""
    return asyncio.run(_run(transcript))


def _to_result(state: dict) -> AssistantResult:
    return AssistantResult(
        transcript=state.get("transcript", ""),
        intent=state.get("intent"),
        plan=state.get("plan"),
        answer_text=state.get("answer_text", ""),
        products=state.get("products", []),
        citations=state.get("citations", []),
        steps=state.get("steps", []),
    )


if __name__ == "__main__":
    result = run_graph("Find me a 500 piece jigsaw puzzle under twenty dollars.")
    for s in result.steps:
        print(f"[{s.status:>9}] {s.node:<10} tool={s.tool or '-':<12} {s.duration_ms}ms  {s.detail}")
    print(f"\nanswer: {result.answer_text}")
