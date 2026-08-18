"""Natural, claim-free dialogue for clarification and preference turns."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Literal

from pydantic import BaseModel, Field

from graph.llm import get_llm, load_prompt
from graph.response_style import (
    clarification_reply,
    preference_clarification_reply,
    refinement_reply,
)


DialogueKind = Literal["clarification", "preference", "refinement", "no_match"]


_FAILURE_PREAMBLE = re.compile(
    r"^(?:"
    r"(?:i(?:'m| am)\s+)?sorry\b|apolog(?:y|ies|ize)\b|unfortunately\b|"
    r"(?:i'm|we're)\s+(?:unable|struggling|having\s+trouble)\b|"
    r"(?:i|we)\s+(?:"
    r"(?:can(?:not|'t)|could(?:not|n't)|(?:am|are|was|were)\s+"
    r"(?:not\s+able|unable)|do(?:\s+not|n't)|did(?:\s+not|n't))\s+"
    r"(?:understand|find|verify|narrow|identify|determine|tell|figure)\b|"
    r"(?:am|'m|are|'re)\s+(?:unable|struggling|having\s+trouble)\b|"
    r"(?:fail|failed)\s+to\s+"
    r"(?:understand|find|verify|narrow|identify|determine)\b|"
    r"do(?:\s+not|n't)\s+have\s+enough\s+(?:information|detail)\b"
    r")|"
    r"(?:this|that|your|the)\s+(?:request|query|description)\s+"
    r"(?:is|was|seems?)\s+(?:too\s+)?"
    r"(?:vague|unclear|broad|underspecified)\b"
    r")",
    re.IGNORECASE,
)


class _DialogueOutput(BaseModel):
    answer_text: str = Field(
        description="A natural response of at most 30 words with one useful question"
    )


def _llm_configured() -> bool:
    if os.getenv("DIALOGUE_LLM", "1").strip().lower() in {"0", "false", "off"}:
        return False
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    key_name = "OPENAI_API_KEY" if provider == "openai" else "ANTHROPIC_API_KEY"
    return bool(os.getenv(key_name, "").strip())


def _fallback(kind: DialogueKind, transcript: str, budget_max: float | None) -> str:
    if kind == "refinement":
        return refinement_reply(budget_max)
    if kind == "preference":
        return preference_clarification_reply(transcript, budget_max)
    if kind == "no_match":
        budget_note = (
            f" while keeping your ${budget_max:,.0f} limit"
            if budget_max is not None
            else ""
        )
        return (
            "What would you like to specify"
            f"{budget_note}—product type, brand, or a key feature?"
        )
    return clarification_reply(budget_max, transcript=transcript)


def _valid_dialogue(
    kind: DialogueKind,
    text: str,
    budget_max: float | None,
) -> bool:
    answer = str(text or "").strip()
    if not answer or len(answer.split()) > 30 or answer.count("?") != 1:
        return False
    normalized = answer.casefold().replace("’", "'")
    if (
        kind in {"clarification", "no_match"}
        and _FAILURE_PREAMBLE.search(normalized)
    ):
        return False
    if re.search(
        r"\b(?:i|we)\s+(?:found|searched|checked)\b|"
        r"\b(?:is|are)\s+(?:available|in stock)\b|\b(?:costs?|rated)\b",
        answer,
        re.IGNORECASE,
    ):
        return False
    stated_numbers = {
        float(value.replace(",", ""))
        for value in re.findall(r"\d[\d,]*(?:\.\d+)?", answer)
    }
    allowed_numbers = {float(budget_max)} if budget_max is not None else set()
    return stated_numbers.issubset(allowed_numbers)


async def natural_dialogue_reply(
    kind: DialogueKind,
    transcript: str,
    budget_max: float | None,
    *,
    previous_request: str = "",
    previous_answer: str = "",
    allow_llm: bool = True,
    llm_factory=get_llm,
) -> str:
    """Generate one contextual question, falling back without product claims."""
    fallback = _fallback(kind, transcript, budget_max)
    if not allow_llm or not _llm_configured():
        return fallback
    human = (
        f"Dialogue kind: {kind}\n"
        f"Known budget maximum: {budget_max if budget_max is not None else 'none'}\n"
        "<previous_request>\n"
        f"{previous_request or 'none'}\n"
        "</previous_request>\n"
        "<previous_assistant_answer>\n"
        f"{previous_answer or 'none'}\n"
        "</previous_assistant_answer>\n"
        "<shopper_turn>\n"
        f"{transcript}\n"
        "</shopper_turn>"
    )
    try:
        llm = llm_factory().with_structured_output(_DialogueOutput)
        output = await asyncio.wait_for(
            llm.ainvoke(
                [("system", load_prompt("dialogue")), ("human", human)]
            ),
            timeout=max(0.5, float(os.getenv("DIALOGUE_LLM_TIMEOUT_S", "6.0"))),
        )
    except Exception:
        return fallback
    return output.answer_text.strip() if _valid_dialogue(
        kind,
        output.answer_text,
        budget_max,
    ) else fallback
