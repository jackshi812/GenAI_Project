"""Presentation-safe labels derived from evidence configuration."""

from __future__ import annotations

import os

from contracts import AssistantResult


def source_mode_label(result: AssistantResult | None = None) -> str:
    """Describe returned evidence without exposing credential values."""
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
            return "Live MCP · No matched web evidence"
        serper_mode = (
            "Live Serper"
            if os.getenv("SERPER_API_KEY", "").strip()
            else "Recorded Serper"
        )
        return f"Live MCP · {serper_mode}"
    return f"Invalid TOOL_MODE · {tool_mode or 'empty'}"


def live_evidence_notice(result: AssistantResult) -> tuple[str, str]:
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
