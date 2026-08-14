"""Tests for LiveKit browser room configuration and token grants."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from livekit import api

from app.livekit_component import create_room_token, settings_from_env


class LiveKitComponentTests(unittest.TestCase):
    def test_missing_cloud_settings_use_documented_local_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = settings_from_env()

        self.assertTrue(settings.local)
        self.assertEqual(settings.url, "ws://127.0.0.1:7880")
        self.assertEqual(settings.api_key, "devkey")

    def test_partial_cloud_settings_are_rejected(self) -> None:
        with patch.dict(os.environ, {"LIVEKIT_URL": "wss://example.livekit.cloud"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "must be set together"):
                settings_from_env()

    def test_token_can_join_only_the_dispatched_agent_room(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = settings_from_env()
        token = create_room_token(
            settings,
            room_name="product-room",
            identity="shopper-test",
        )
        claims = api.TokenVerifier("devkey", "secret").verify(token)

        self.assertEqual(claims.identity, "shopper-test")
        self.assertTrue(claims.video.room_join)
        self.assertEqual(claims.video.room, "product-room")
        self.assertEqual(
            claims.room_config.agents[0].agent_name,
            "product-discovery",
        )


if __name__ == "__main__":
    unittest.main()
