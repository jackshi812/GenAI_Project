"""Router and Planner nodes (GRAPH-01, GRAPH-02, GRAPH-03)."""

from contracts import ShoppingContext

from graph.decision import choose_direction, choose_product_index
from graph.dialogue import natural_dialogue_reply
from graph.fast_reply import extract_budget_bounds
from graph.llm import get_llm, load_prompt
from graph.matching import currency_keyword_hit  # deterministic GRAPH-03 check
from graph.preferences import (
    clears_budget,
    has_actionable_preference,
    resolve_preferences,
)
from graph.relevance import infer_catalog_category
from graph.response_style import (
    CLARIFICATION_PLAN,
    REFINEMENT_PLAN,
    is_delegated_choice,
    is_rejection_followup,
    is_vague_shopping_query,
    refinement_reply,
)
from graph.retriever import RAG_CANDIDATE_K
from graph.safety import (
    SAFETY_FLAG,
    SAFETY_RATIONALE,
    is_hazardous_chemical_mixing,
)
from graph.state import PlannerOutput, RouterOutput, make_step, timer


async def router_node(state: dict) -> dict:
    """Extract task, constraints, and safety flags from the transcript."""
    transcript = str(state.get("transcript") or "")
    hazardous = is_hazardous_chemical_mixing(transcript)
    explicit_delegated = not hazardous and is_delegated_choice(transcript)
    explicit_actionable_preference = has_actionable_preference(transcript)
    rejection = not hazardous and is_rejection_followup(transcript)
    bare_rejection = bool(
        rejection and not explicit_actionable_preference and not explicit_delegated
    )
    with timer() as t:
        if hazardous:
            out = RouterOutput(task="", safety_flags=[SAFETY_FLAG])
        else:
            llm = get_llm().with_structured_output(RouterOutput)
            out = await llm.ainvoke(
                [
                    ("system", load_prompt("router")),
                    ("human", transcript),
                ]
            )
    dialogue_context = state.get("dialogue_context") or {}
    delegated = not out.safety_flags and explicit_delegated
    prior_shopping_context = dialogue_context.get("shopping_context")
    if out.safety_flags or bare_rejection:
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
    elif delegated and prior_shopping_context is not None:
        shopping_context = ShoppingContext.model_validate(prior_shopping_context)
    else:
        shopping_context = await resolve_preferences(
            transcript,
            out.task,
            prior_shopping_context,
            allow_llm=not delegated,
        )
    prior_products = list(dialogue_context.get("products") or [])
    selection_index: int | None = None
    decision_source = ""
    direction = None
    if delegated and prior_products and not dialogue_context.get(
        "rejected_previous", False
    ):
        selection_index, decision_source = await choose_product_index(
            state["transcript"],
            prior_products,
        )
    elif delegated:
        direction = await choose_direction(state["transcript"], dialogue_context)
        decision_source = direction.selected_by
        shopping_context = ShoppingContext(
            product_query=direction.query,
            resolved_query=direction.query,
            understanding_source=(
                "llm" if direction.selected_by == "llm" else "fallback"
            ),
        )

    actionable_preference = (
        not out.safety_flags
        and not delegated
        and (
            explicit_actionable_preference
            or shopping_context.preference_changed
        )
    )
    refinement = (
        not out.safety_flags
        and not delegated
        and rejection
        and not actionable_preference
    )
    incomplete_preference = bool(
        prior_shopping_context is not None
        and shopping_context.is_followup
        and not shopping_context.preference_changed
        and not refinement
        and not delegated
    )
    parsed_budget_min, parsed_budget_max = extract_budget_bounds(state["transcript"])
    budget_min = (
        parsed_budget_min if parsed_budget_min is not None else out.budget_min
    )
    budget_max = (
        parsed_budget_max if parsed_budget_max is not None else out.budget_max
    )
    if clears_budget(state["transcript"]):
        budget_min = None
        budget_max = None
    if budget_max is None and not clears_budget(state["transcript"]) and (
        refinement or delegated or shopping_context.is_followup
    ):
        budget_min = dialogue_context.get("budget_min")
        budget_max = dialogue_context.get("budget_max")
    task = (
        ""
        if out.safety_flags
        else direction.query
        if direction is not None
        else ""
        if selection_index is not None
        else shopping_context.resolved_query or out.task
    )
    category = (
        None
        if out.safety_flags
        else direction.category
        if direction is not None
        else out.category or infer_catalog_category(task)
    )
    constraints = {
        "budget_max": budget_max,
        "budget_min": budget_min,
        "category": category,
        "brand": None if delegated else out.brand,
        "material": (
            shopping_context.materials[0]
            if shopping_context.materials
            else out.material
        ),
    }
    detail = f"task={task!r}"
    if delegated:
        detail += f" delegated_choice={decision_source or 'fallback'}"
    stated = {k: v for k, v in constraints.items() if v is not None}
    if stated:
        detail += " " + ", ".join(f"{k}={v}" for k, v in stated.items())
    if out.safety_flags:
        detail += f" safety={out.safety_flags}"
    vague = (
        not out.safety_flags
        and not refinement
        and not delegated
        and (
            incomplete_preference
            or is_vague_shopping_query(shopping_context.product_query or task)
        )
    )
    turn_kind = (
        "safety"
        if out.safety_flags
        else "selection"
        if selection_index is not None
        else "refinement"
        if refinement
        else "clarification"
        if vague
        else "preference_update"
        if actionable_preference and shopping_context.preference_changed
        else "shopping"
    )
    previous_request = str(dialogue_context.get("previous_request") or "")
    conversation_answer = ""
    if refinement:
        conversation_answer = refinement_reply(budget_max)
    elif incomplete_preference:
        conversation_answer = await natural_dialogue_reply(
            "preference",
            state["transcript"],
            budget_max,
            previous_request=previous_request,
        )
    elif vague:
        conversation_answer = await natural_dialogue_reply(
            "clarification",
            state["transcript"],
            budget_max,
            previous_request=previous_request,
        )
    return {
        "intent": task,
        "constraints": constraints,
        "safety_flags": out.safety_flags,
        "turn_kind": turn_kind,
        "decision_delegated": delegated,
        "decision_source": decision_source,
        "selected_product_index": selection_index or 0,
        "shopping_context": shopping_context,
        "conversation_answer": conversation_answer,
        "steps": [make_step("router", None, "completed", t.ms, detail, t.started_at)],
    }


async def planner_node(state: dict) -> dict:
    """Choose sources and build the retrieval filter."""
    transcript = state["transcript"]
    constraints = state.get("constraints", {})

    # Safety stop: no planner LLM call, no retrieval (fixed rationale).
    if SAFETY_FLAG in (state.get("safety_flags") or []):
        return {
            "plan": SAFETY_RATIONALE,
            "use_private": False,
            "use_live": False,
            "filters": {},
            "semantic_query": "",
            "steps": [make_step("planner", None, "completed", 0, SAFETY_RATIONALE)],
        }

    if state.get("turn_kind") in {"clarification", "refinement", "selection"}:
        plan = (
            "Agent decision; choose among the retained grounded results without searching."
            if state.get("turn_kind") == "selection"
            else REFINEMENT_PLAN
            if state.get("turn_kind") == "refinement"
            else CLARIFICATION_PLAN
        )
        return {
            "plan": plan,
            "use_private": False,
            "use_live": False,
            "filters": {},
            "semantic_query": state.get("intent") or "",
            "steps": [
                make_step(
                    "planner",
                    None,
                    "completed",
                    0,
                    plan,
                )
            ],
        }

    if state.get("decision_delegated"):
        filters = {
            "price_max": constraints.get("budget_max"),
            "price_min": constraints.get("budget_min"),
            "category": constraints.get("category"),
            "brand": constraints.get("brand"),
            "k": RAG_CANDIDATE_K,
        }
        filters = {key: value for key, value in filters.items() if value is not None}
        plan = (
            f"Agent-selected direction ({state.get('decision_source') or 'fallback'}): "
            "search the private catalog; compose only from returned evidence."
        )
        return {
            "plan": plan,
            "use_private": True,
            "use_live": False,
            "filters": filters,
            "semantic_query": state.get("intent") or "",
            "steps": [make_step("planner", None, "completed", 0, plan)],
        }

    # Deterministic escalation FIRST — cannot be talked out of firing.
    keyword_live = currency_keyword_hit(transcript)

    with timer() as t:
        llm = get_llm().with_structured_output(PlannerOutput)
        out: PlannerOutput = await llm.ainvoke(
            [
                ("system", load_prompt("planner")),
                (
                    "human",
                    f"Transcript: {transcript}\n"
                    f"Extracted task: {state.get('intent')}\n"
                    f"Constraints: { {k: v for k, v in constraints.items() if v is not None} }\n"
                    f"Deterministic currency-keyword hit: {keyword_live}",
                ),
            ]
        )

    use_live = keyword_live or out.use_live

    # Filters are built deterministically from the Router's extracted
    # constraints — never from planner-LLM improvisation. An invented
    # category (e.g. "500-piece jigsaw puzzle" instead of the real catalog
    # category "Toys & Games") silently filters out every correct result.
    # The LLM contributes only k, the result count.
    filters = {
        "price_max": constraints.get("budget_max"),
        "price_min": constraints.get("budget_min"),
        "category": constraints.get("category"),
        "brand": constraints.get("brand"),
        "k": max(out.filters.k or RAG_CANDIDATE_K, RAG_CANDIDATE_K),
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    # Semantic query built deterministically: task phrase + stated material.
    # Never the raw transcript, never budgets or escalation words.
    semantic_query = (state.get("intent") or "").strip()
    material = constraints.get("material")
    if material and material.lower() not in semantic_query.lower():
        semantic_query = f"{semantic_query} {material}".strip()

    plan_sentence = out.rationale or "Consult the private catalog."
    if keyword_live:
        plan_sentence += " Live search forced by a currency keyword in the request."

    return {
        "plan": plan_sentence,
        "use_private": out.use_private,
        "use_live": use_live,
        "filters": filters,
        "semantic_query": semantic_query,
        "steps": [make_step("planner", None, "completed", t.ms, plan_sentence, t.started_at)],
    }
