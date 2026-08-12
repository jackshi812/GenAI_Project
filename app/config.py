"""Presentation-safe labels derived from evidence configuration."""

from __future__ import annotations

import os


def source_mode_label() -> str:
    """Describe evidence configuration without exposing credential values."""
    tool_mode = os.getenv("TOOL_MODE", "live").strip().lower()
    if tool_mode == "fixture":
        return "Fixture graph · Recorded data"
    if tool_mode == "live":
        serper_mode = (
            "Live Serper"
            if os.getenv("SERPER_API_KEY", "").strip()
            else "Recorded Serper"
        )
        return f"Live MCP · {serper_mode}"
    return f"Invalid TOOL_MODE · {tool_mode or 'empty'}"
