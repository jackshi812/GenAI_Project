"""Regression checks for user-visible evidence-source labels."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.config import source_mode_label


class SourceModeLabelTests(unittest.TestCase):
    def test_fixture_mode_is_explicitly_recorded(self) -> None:
        with patch.dict(os.environ, {"TOOL_MODE": "fixture"}, clear=True):
            self.assertEqual(source_mode_label(), "Fixture graph · Recorded data")

    def test_live_mcp_with_key_is_live_serper(self) -> None:
        with patch.dict(
            os.environ,
            {"TOOL_MODE": "live", "SERPER_API_KEY": "configured"},
            clear=True,
        ):
            self.assertEqual(source_mode_label(), "Live MCP · Live Serper")

    def test_live_mcp_without_key_is_recorded_serper(self) -> None:
        with patch.dict(os.environ, {"TOOL_MODE": "live"}, clear=True):
            self.assertEqual(source_mode_label(), "Live MCP · Recorded Serper")


if __name__ == "__main__":
    unittest.main()
