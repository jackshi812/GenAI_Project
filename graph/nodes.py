"""Router and Planner nodes (GRAPH-01, GRAPH-02, GRAPH-03)."""

from graph.llm import get_llm, load_prompt
from graph.matching import currency_keyword_hit  # deterministic GRAPH-03 check
from graph.state import PlannerOutput, RouterOutput, make_step, timer

SAFETY_FLAG = "hazardous_chemical_mixing"
SAFETY_RATIONALE = "Safety stop: I can't recommend hazardous chemical mixing."


async def router_node(state: dict) -> dict:
    """Extract task, constraints, and safety flags from the transcript."""
    with timer() as t:
        llm = get_llm().with_structured_output(RouterOutput)
        out: RouterOutput = await llm.ainvoke(
            [
                ("system", load_prompt("router")),
                ("human", state["transcript"]),
            ]
        )
    constraints = {
        "budget_max": out.budget_max,
        "budget_min": out.budget_min,
        "category": out.category,
        "brand": out.brand,
        "material": out.material,
    }
    detail = f"task={out.task!r}"
    stated = {k: v for k, v in constraints.items() if v is not None}
    if stated:
        detail += " " + ", ".join(f"{k}={v}" for k, v in stated.items())
    if out.safety_flags:
        detail += f" safety={out.safety_flags}"
    return {
        "intent": out.task,
        "constraints": constraints,
        "safety_flags": out.safety_flags,
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

    # Filters: only catalog-supported keys; budgets come deterministically
    # from the Router's numeric constraints (never embedding text).
    filters = dict(out.filters or {})
    if constraints.get("budget_max") is not None:
        filters["price_max"] = constraints["budget_max"]
    if constraints.get("budget_min") is not None:
        filters["price_min"] = constraints["budget_min"]
    if constraints.get("category") and "category" not in filters:
        filters["category"] = constraints["category"]
    if constraints.get("brand") and "brand" not in filters:
        filters["brand"] = constraints["brand"]
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
