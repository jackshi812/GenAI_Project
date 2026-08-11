"""LangGraph state schema and graph-internal models.

`StepEvent` (and every other UI-facing model) is imported from `contracts.py`
at the repository root — never redefined here (D-10). `RouterOutput` and
`PlannerOutput` never reach the UI, so they live on this side of the seam.
"""

import operator
import time
from datetime import datetime, timezone
from typing import Annotated, Any, Optional, TypedDict

from pydantic import BaseModel, Field

from contracts import StepEvent


class GraphState(TypedDict, total=False):
    transcript: str
    intent: str
    constraints: dict
    safety_flags: list[str]
    plan: str
    semantic_query: str
    filters: dict
    use_live: bool
    use_private: bool
    rag_results: list
    web_results: list
    products: list
    answer_text: str
    citations: list
    # Append reducer: LangGraph overwrites keys by default; operator.add makes
    # each node's returned events accumulate in execution order. Nodes return
    # {"steps": [event]} and never mutate the incoming list (D-14).
    steps: Annotated[list[StepEvent], operator.add]


class RouterOutput(BaseModel):
    """Structured output of the Router LLM call. Graph-internal."""

    task: str = Field(description="Short product phrase, no budget or currency words")
    budget_max: Optional[float] = None
    budget_min: Optional[float] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    material: Optional[str] = None
    safety_flags: list[str] = Field(default_factory=list)


class PlannerOutput(BaseModel):
    """Structured output of the Planner LLM call. Graph-internal."""

    use_private: bool = True
    use_live: bool = False
    filters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_step(
    node: str,
    tool: Optional[str],
    status: str,
    duration_ms: Optional[int],
    detail: str,
    started_at: Optional[str] = None,
) -> StepEvent:
    """Construct a StepEvent. Never appends to or mutates state["steps"].

    Pass timer.started_at when the step was timed; otherwise the construction
    moment is used (instant steps like skips)."""
    return StepEvent(
        node=node,
        tool=tool,
        status=status,
        duration_ms=int(duration_ms) if duration_ms is not None else None,
        detail=detail,
        started_at=started_at or _now_iso(),
    )


class timer:
    """Context manager measuring wall time in ms for step events, recording
    the true start timestamp for StepEvent.started_at."""

    def __enter__(self):
        self.started_at = _now_iso()
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = int((time.perf_counter() - self._t0) * 1000)
        return False
