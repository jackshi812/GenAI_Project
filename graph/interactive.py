"""Low-latency deterministic nodes for the interactive LangGraph path.

The assignment-required graph stages remain visible and tool-aware. This mode
removes sequential LLM round trips from the user-facing path by deriving every
claim and citation directly from retrieved evidence. The prompt-heavy graph is
still available through ``GRAPH_MODE=llm``.
"""

from __future__ import annotations

import re

from graph.answer import _build_citations, _degraded_answer
from graph.fast_reply import (
    conversation_reply,
    extract_brand,
    extract_budget_max,
    semantic_query,
    should_search_live,
)
from graph.nodes import SAFETY_FLAG, SAFETY_RATIONALE
from graph.relevance import GROCERY_TERMS, normalized_terms
from graph.state import make_step, timer


_HAZARDOUS_MIX = re.compile(
    r"(?:\b(?:mix|combine)\b.{0,80}\b(?:bleach|chlorine)\b.{0,80}"
    r"\b(?:ammonia|acid|vinegar)\b)|"
    r"(?:\b(?:ammonia|acid|vinegar)\b.{0,80}\b(?:mix|combine)\b.{0,80}"
    r"\b(?:bleach|chlorine)\b)",
    re.IGNORECASE,
)


async def interactive_router_node(state: dict) -> dict:
    """Extract common shopping intent and safety constraints without an LLM."""
    transcript = str(state.get("transcript") or "").strip()
    with timer() as measured:
        social_answer = conversation_reply(transcript)
        hazardous = bool(_HAZARDOUS_MIX.search(transcript))
        query = "" if social_answer or hazardous else semantic_query(transcript)
        budget_max = extract_budget_max(transcript)
        brand = extract_brand(transcript) if query else None
        terms = normalized_terms(query)
        category = "Grocery & Gourmet Food" if terms & GROCERY_TERMS else None

    safety_flags = [SAFETY_FLAG] if hazardous else []
    turn_kind = "conversation" if social_answer else "shopping"
    if hazardous:
        turn_kind = "safety"
    constraints = {
        "budget_max": budget_max,
        "budget_min": None,
        "category": category,
        "brand": brand,
        "material": None,
    }
    stated = {key: value for key, value in constraints.items() if value is not None}
    detail = f"turn={turn_kind} intent={query!r}"
    if stated:
        detail += f" constraints={stated}"
    if safety_flags:
        detail += f" safety={safety_flags}"
    return {
        "intent": query,
        "constraints": constraints,
        "safety_flags": safety_flags,
        "turn_kind": turn_kind,
        "conversation_answer": social_answer or "",
        "steps": [
            make_step(
                "router",
                None,
                "completed",
                measured.ms,
                detail,
                measured.started_at,
            )
        ],
    }


async def interactive_planner_node(state: dict) -> dict:
    """Build the MCP retrieval plan from deterministic router output."""
    with timer() as measured:
        turn_kind = state.get("turn_kind") or "shopping"
        constraints = state.get("constraints") or {}
        if turn_kind == "safety":
            plan = SAFETY_RATIONALE
            use_private = False
            use_live = False
            filters = {}
        elif turn_kind == "conversation":
            plan = "Conversational turn; product tools are not needed."
            use_private = False
            use_live = False
            filters = {}
        else:
            use_private = True
            use_live = should_search_live(state["transcript"])
            filters = {
                "price_max": constraints.get("budget_max"),
                "price_min": constraints.get("budget_min"),
                "category": constraints.get("category"),
                "brand": constraints.get("brand"),
                "k": 5,
            }
            filters = {key: value for key, value in filters.items() if value is not None}
            plan = "Search the private catalog"
            if use_live:
                plan += " and check one current web query"
            plan += "; compose the answer only from returned evidence."

    return {
        "plan": plan,
        "use_private": use_private,
        "use_live": use_live,
        "filters": filters,
        "semantic_query": state.get("intent") or "",
        "steps": [
            make_step(
                "planner",
                None,
                "completed",
                measured.ms,
                plan,
                measured.started_at,
            )
        ],
    }


async def interactive_answerer_node(state: dict) -> dict:
    """Compose an evidence-only answer and validate its citations locally."""
    with timer() as measured:
        turn_kind = state.get("turn_kind") or "shopping"
        products = state.get("products") or []
        if turn_kind == "safety":
            answer_text = SAFETY_RATIONALE
            citations = []
            detail = "Fixed safety answer; no product claims."
        elif turn_kind == "conversation":
            answer_text = state.get("conversation_answer") or (
                "Hi! What are you shopping for today?"
            )
            citations = []
            detail = "Fixed conversational answer; no product claims."
        elif not products:
            answer_text = "I couldn’t find a grounded product for that request."
            citations = []
            detail = "No products; no claims or citations."
        else:
            draft = _degraded_answer(products)
            answer_text = draft.answer_text
            citations = _build_citations(draft, products)
            detail = (
                f"evidence-only answer={len(answer_text.split())} words, "
                f"{len(citations)} validated citations"
            )

    return {
        "answer_text": answer_text,
        "citations": citations,
        "steps": [
            make_step(
                "answerer",
                None,
                "completed",
                measured.ms,
                detail,
                measured.started_at,
            )
        ],
    }
