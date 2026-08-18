"""Presentation-safe labels derived from evidence configuration."""

from __future__ import annotations

import os
from typing import Literal

from contracts import AssistantResult, StepEvent


NoticeKind = Literal["caption", "warning"]


def clarification_needed(result: AssistantResult | None) -> bool:
    """Identify turns intentionally paused before retrieval for more detail."""
    if result is None or result.products:
        return False
    if "clarifying question" in str(result.plan or "").casefold():
        return True
    return any(
        "turn=clarification" in step.detail.casefold()
        for step in result.steps
    )


def refinement_needed(result: AssistantResult | None) -> bool:
    """Identify feedback turns waiting for a concrete preference change."""
    if result is None:
        return False
    if "preference refinement" in str(result.plan or "").casefold():
        return True
    return any(
        "turn=refinement" in step.detail.casefold()
        for step in result.steps
    )


def source_mode_label(result: AssistantResult | None = None) -> str:
    """Describe returned evidence without exposing credential values."""
    if refinement_needed(result):
        return "Refining your choices · Search paused"
    if clarification_needed(result):
        return "Clarification needed · Search not started"
    tool_mode = os.getenv("TOOL_MODE", "live").strip().lower()
    if tool_mode == "fixture":
        return "Fixture graph · Recorded data"
    if tool_mode == "live":
        if result is not None:
            origins = {
                product.live.origin
                for product in result.products
                if product.live is not None
            }
            if origins == {"live_serper"}:
                return "Live MCP · Live Serper"
            if "recorded_fixture" in origins:
                return "Live MCP · Recorded Serper"
            if origins:
                return "Live MCP · Unverified web evidence"
            web_steps = [step for step in result.steps if step.tool == "web.search"]
            if not web_steps:
                return "Live MCP · Catalog only (web not requested)"
            if any(step.status == "error" for step in web_steps):
                return "Live MCP · Web lookup incomplete"
            return "Live MCP · No confirmed web match"
        serper_mode = (
            "Live Serper"
            if os.getenv("SERPER_API_KEY", "").strip()
            else "Recorded Serper"
        )
        return f"Live MCP · {serper_mode}"
    return f"Invalid TOOL_MODE · {tool_mode or 'empty'}"


def live_evidence_notice(result: AssistantResult) -> tuple[NoticeKind, str]:
    """Describe absent live citations without overstating retrieval success."""
    web_steps = [step for step in result.steps if step.tool == "web.search"]
    if not web_steps:
        return "caption", "Live lookup was not requested for this result."
    if any(step.status == "error" for step in web_steps):
        return "warning", "Live lookup failed; only grounded catalog evidence is shown."
    if any(step.status == "completed" for step in web_steps):
        return (
            "warning",
            "Live lookup completed, but no product match was confirmed.",
        )
    return "warning", "Live lookup did not complete; no live evidence is shown."


def product_live_notice(web_step: StepEvent | None) -> tuple[str, str]:
    """Explain a missing per-product match without implying delisting."""
    if web_step is None:
        return (
            "Live search not requested",
            "Ask about current price, availability, ratings, or reviews to compare this item.",
        )
    if web_step.status == "error":
        return (
            "Live search unavailable",
            "The catalog result is still shown; no live evidence was used.",
        )
    if web_step.status == "completed":
        return (
            "No confirmed live match",
            "Results were checked, but none could be verified as this exact product.",
        )
    return (
        "Live search incomplete",
        "No live evidence was used for this product.",
    )
