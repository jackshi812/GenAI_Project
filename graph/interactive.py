"""Low-latency deterministic nodes for the interactive LangGraph path.

The assignment-required graph stages remain visible and tool-aware. Common
constraints stay local and fast; ambiguous preference changes and final prose
may each use one bounded call to the configured LLM. Every accepted claim and
citation still comes from retrieved evidence. The prompt-heavy graph remains
available through ``GRAPH_MODE=llm``.
"""

from __future__ import annotations

from contracts import ShoppingContext
from graph.answer import _build_citations, _degraded_answer, natural_answer_once
from graph.decision import choose_direction, choose_product_index
from graph.dialogue import natural_dialogue_reply
from graph.fast_reply import (
    conversation_reply,
    explicitly_requests_live,
    extract_brand,
    extract_budget_bounds,
    semantic_query,
    should_search_live,
)
from graph.preferences import (
    clears_budget,
    has_actionable_preference,
    preference_requirements,
    resolve_preferences,
    with_product_query,
)
from graph.recommendation import build_top_recommendation, canonicalize_products
from graph.relevance import infer_catalog_category
from graph.retriever import RAG_CANDIDATE_K
from graph.safety import (
    SAFETY_FLAG,
    SAFETY_RATIONALE,
    is_hazardous_chemical_mixing,
)
from graph.response_style import (
    CLARIFICATION_PLAN,
    REFINEMENT_PLAN,
    clarification_reply,
    is_delegated_choice,
    is_rejection_followup,
    is_vague_shopping_query,
    refinement_reply,
)
from graph.state import make_step, timer


async def interactive_router_node(state: dict) -> dict:
    """Extract common shopping intent and safety constraints without an LLM."""
    transcript = str(state.get("transcript") or "").strip()
    dialogue_context = state.get("dialogue_context") or {}
    with timer() as measured:
        hazardous = is_hazardous_chemical_mixing(transcript)
        explicit_delegated = not hazardous and is_delegated_choice(transcript)
        explicit_actionable_preference = has_actionable_preference(transcript)
        rejection = not hazardous and is_rejection_followup(transcript)
        bare_rejection = bool(
            rejection
            and not explicit_actionable_preference
            and not explicit_delegated
        )
        prior_shopping_context = dialogue_context.get("shopping_context")
        base_query = semantic_query(transcript)
        social_answer = (
            None if hazardous or explicit_delegated else conversation_reply(transcript)
        )
        if social_answer:
            shopping_context = (
                ShoppingContext.model_validate(prior_shopping_context)
                if prior_shopping_context is not None
                else ShoppingContext()
            )
        elif hazardous or explicit_delegated or bare_rejection:
            shopping_context = (
                ShoppingContext.model_validate(prior_shopping_context)
                if prior_shopping_context is not None
                else ShoppingContext()
            )
            if bare_rejection:
                shopping_context = shopping_context.model_copy(
                    update={
                        "is_followup": prior_shopping_context is not None,
                        "preference_changed": False,
                    },
                    deep=True,
                )
        else:
            shopping_context = await resolve_preferences(
                transcript,
                base_query,
                prior_shopping_context,
                previous_answer=str(dialogue_context.get("previous_answer") or ""),
            )
        delegated = explicit_delegated or bool(
            not hazardous
            and not social_answer
            and is_vague_shopping_query(shopping_context.product_query)
            and (
                preference_requirements(shopping_context)
                or shopping_context.excluded
            )
        )
        actionable_preference = (
            not hazardous
            and not delegated
            and (
                explicit_actionable_preference
                or bool(shopping_context.preference_changed)
            )
        )
        refinement = (
            not hazardous
            and not delegated
            and rejection
            and not actionable_preference
        )
        incomplete_preference = bool(
            prior_shopping_context is not None
            and shopping_context.is_followup
            and not shopping_context.preference_changed
            and not actionable_preference
            and not refinement
            and not delegated
            and not social_answer
        )
        prior_products = list(dialogue_context.get("products") or [])
        selection_index: int | None = None
        decision_source = ""
        direction = None
        if delegated and prior_products and not dialogue_context.get(
            "rejected_previous", False
        ):
            selection_index, decision_source = await choose_product_index(
                transcript,
                prior_products,
            )
        elif delegated:
            active_context = (
                ShoppingContext.model_validate(prior_shopping_context)
                if prior_shopping_context is not None
                else None
            )
            can_continue_active_search = bool(
                active_context is not None
                and not prior_products
                and not dialogue_context.get("rejected_previous", False)
                and not is_vague_shopping_query(active_context.product_query)
            )
            if can_continue_active_search:
                shopping_context = active_context.model_copy(
                    update={"is_followup": True},
                    deep=True,
                )
                decision_source = "active request"
            else:
                direction = await choose_direction(transcript, dialogue_context)
                decision_source = direction.selected_by
                shopping_context = with_product_query(
                    shopping_context,
                    direction.query,
                    understanding_source=(
                        "llm" if direction.selected_by == "llm" else "fallback"
                    ),
                )

        social_answer = None if refinement or delegated else social_answer
        if direction is not None:
            query = shopping_context.resolved_query
        elif social_answer or hazardous or refinement or selection_index is not None:
            query = ""
        else:
            query = shopping_context.resolved_query or base_query
        budget_min, budget_max = extract_budget_bounds(transcript)
        if clears_budget(transcript):
            budget_min = None
            budget_max = None
        elif budget_max is None and (
            refinement or delegated or shopping_context.is_followup
        ):
            budget_min = dialogue_context.get("budget_min")
            budget_max = dialogue_context.get("budget_max")
        previous_request = str(dialogue_context.get("previous_request") or "")
        previous_answer = str(dialogue_context.get("previous_answer") or "")
        clarification_answer = ""
        if incomplete_preference:
            clarification_answer = await natural_dialogue_reply(
                "preference",
                transcript,
                budget_max,
                previous_request=previous_request,
                previous_answer=previous_answer,
            )
        elif query and is_vague_shopping_query(
            shopping_context.product_query or query
        ):
            clarification_answer = await natural_dialogue_reply(
                "clarification",
                transcript,
                budget_max,
                previous_request=previous_request,
                previous_answer=previous_answer,
            )
        refinement_answer = refinement_reply(budget_max) if refinement else ""
        brand = extract_brand(transcript) if query and not delegated else None
        category = (
            direction.category
            if direction is not None
            else infer_catalog_category(query)
        )

    safety_flags = [SAFETY_FLAG] if hazardous else []
    turn_kind = "conversation" if social_answer else "shopping"
    if hazardous:
        turn_kind = "safety"
    elif selection_index is not None:
        turn_kind = "selection"
    elif refinement_answer:
        turn_kind = "refinement"
    elif clarification_answer:
        turn_kind = "clarification"
    elif actionable_preference and shopping_context.preference_changed:
        turn_kind = "preference_update"
    constraints = {
        "budget_max": budget_max,
        "budget_min": budget_min,
        "category": category,
        "brand": brand,
        "material": None,
    }
    stated = {key: value for key, value in constraints.items() if value is not None}
    detail = (
        f"turn={turn_kind} intent={query!r} "
        f"understanding={shopping_context.understanding_source}"
    )
    if delegated:
        detail += f" delegated_choice={decision_source or 'fallback'}"
    if stated:
        detail += f" constraints={stated}"
    if safety_flags:
        detail += f" safety={safety_flags}"
    return {
        "intent": query,
        "constraints": constraints,
        "safety_flags": safety_flags,
        "turn_kind": turn_kind,
        "decision_delegated": delegated,
        "decision_source": decision_source,
        "selected_product_index": selection_index or 0,
        "shopping_context": shopping_context,
        "conversation_answer": (
            social_answer or refinement_answer or clarification_answer
        ),
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
        elif turn_kind == "clarification":
            plan = CLARIFICATION_PLAN
            use_private = False
            use_live = False
            filters = {}
        elif turn_kind == "refinement":
            plan = REFINEMENT_PLAN
            use_private = False
            use_live = False
            filters = {}
        elif turn_kind == "selection":
            plan = (
                "Agent decision; choose among the retained grounded results "
                "without starting another search."
            )
            use_private = False
            use_live = False
            filters = {}
        else:
            use_private = True
            # Route on the resolved product intent, not filler-heavy speech.
            # This keeps broad families such as bedding catalog-first while
            # named models such as iPhone 12 still receive a current lookup.
            routing_text = state.get("intent") or state["transcript"]
            use_live = bool(
                (state.get("dialogue_context") or {}).get("force_live")
            ) or (
                explicitly_requests_live(routing_text)
                if preference_requirements(state.get("shopping_context"))
                else should_search_live(routing_text)
            )
            filters = {
                "price_max": constraints.get("budget_max"),
                "price_min": constraints.get("budget_min"),
                "category": constraints.get("category"),
                "brand": constraints.get("brand"),
                "k": RAG_CANDIDATE_K,
            }
            filters = {key: value for key, value in filters.items() if value is not None}
            plan = "Search the private catalog"
            if state.get("decision_delegated"):
                plan = (
                    f"Agent-selected direction ({state.get('decision_source') or 'fallback'}): "
                    "search the private catalog"
                )
            if use_live:
                plan += " and check one current web query"
            plan += "; compose the answer only from returned evidence."
            if state.get("turn_kind") == "preference_update":
                plan += " Rank and compare by the shopper's updated preferences."

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
        elif turn_kind == "clarification":
            answer_text = state.get("conversation_answer") or clarification_reply(
                (state.get("constraints") or {}).get("budget_max")
            )
            citations = []
            detail = "Clarifying question; no product claims or tool calls."
        elif turn_kind == "refinement":
            answer_text = state.get("conversation_answer") or refinement_reply(
                (state.get("constraints") or {}).get("budget_max")
            )
            citations = list(
                (state.get("dialogue_context") or {}).get("citations") or []
            )
            detail = (
                "Preference refinement; previous evidence retained and no tool calls."
            )
        elif turn_kind == "selection":
            selected_index = min(
                max(int(state.get("selected_product_index") or 0), 0),
                max(len(products) - 1, 0),
            )
            selected = products[selected_index:selected_index + 1]
            if selected:
                products = canonicalize_products(products, selected_index)
                canonical_state = {**state, "products": products}
                draft = _degraded_answer(products, canonical_state)
                answer_text = draft.answer_text
                citations = _build_citations(draft, products)
                detail = (
                    f"Agent chose grounded candidate {selected_index + 1} "
                    f"via {state.get('decision_source') or 'fallback'}."
                )
            else:
                answer_text = (
                    "I don’t have grounded options to choose from yet, so I’ll "
                    "pick a shopping direction and search next."
                )
                citations = []
                detail = "No retained products were available for selection."
        elif not products:
            dialogue_context = state.get("dialogue_context") or {}
            answer_text = await natural_dialogue_reply(
                "no_match",
                str(state.get("transcript") or ""),
                (state.get("constraints") or {}).get("budget_max"),
                previous_request=str(dialogue_context.get("previous_request") or ""),
                previous_answer=str(dialogue_context.get("previous_answer") or ""),
            )
            citations = []
            detail = "Natural no-match recovery; no product claims or citations."
        else:
            draft = await natural_answer_once(state, products)
            if draft is not None:
                answer_text = draft.answer_text
                citations = _build_citations(draft, products)
                detail = (
                    f"one-call natural answer={len(answer_text.split())} words, "
                    f"{len(citations)} deterministically validated citations"
                )
            else:
                draft = _degraded_answer(products, state)
                answer_text = draft.answer_text
                citations = _build_citations(draft, products)
                detail = (
                    f"evidence-only answer={len(answer_text.split())} words, "
                    f"{len(citations)} validated citations"
                )

    return {
        "answer_text": answer_text,
        "citations": citations,
        "products": products,
        "top_recommendation": build_top_recommendation(products, state),
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
