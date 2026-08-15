"""Streamlit wrapper for the browser-side LiveKit voice conversation."""

from __future__ import annotations

import datetime
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components
from livekit import api


_FRONTEND = Path(__file__).with_name("livekit_frontend") / "dist"
_voice_component = components.declare_component(
    "livekit_voice", path=str(_FRONTEND)
)


@dataclass(frozen=True)
class LiveKitSettings:
    url: str
    api_key: str
    api_secret: str
    agent_name: str
    local: bool


def settings_from_env() -> LiveKitSettings:
    """Use configured Cloud credentials or LiveKit's documented local defaults."""
    values = {
        "url": os.getenv("LIVEKIT_URL", "").strip(),
        "api_key": os.getenv("LIVEKIT_API_KEY", "").strip(),
        "api_secret": os.getenv("LIVEKIT_API_SECRET", "").strip(),
    }
    configured = [bool(value) for value in values.values()]
    if any(configured) and not all(configured):
        raise RuntimeError(
            "LIVEKIT_URL, LIVEKIT_API_KEY, and LIVEKIT_API_SECRET must be set together"
        )
    if not any(configured):
        values = {
            "url": "ws://127.0.0.1:7880",
            "api_key": "devkey",
            "api_secret": "secret",
        }
        local = True
    else:
        local = values["url"].startswith(("ws://127.0.0.1", "ws://localhost"))
    return LiveKitSettings(
        **values,
        agent_name=os.getenv("LIVEKIT_AGENT_NAME", "product-discovery").strip()
        or "product-discovery",
        local=local,
    )


def create_room_token(
    settings: LiveKitSettings,
    *,
    room_name: str,
    identity: str,
) -> str:
    """Create a short-lived browser token that dispatches this project's agent."""
    room_config = api.RoomConfiguration(
        agents=[api.RoomAgentDispatch(agent_name=settings.agent_name)]
    )
    return (
        api.AccessToken(settings.api_key, settings.api_secret)
        .with_identity(identity)
        .with_name("Shopper")
        .with_ttl(datetime.timedelta(minutes=15))
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .with_room_config(room_config)
        .to_jwt()
    )


def new_room_name() -> str:
    return f"product-discovery-{uuid.uuid4().hex[:12]}"


def new_identity() -> str:
    return f"shopper-{uuid.uuid4().hex[:10]}"


def live_voice(
    *,
    settings: LiveKitSettings,
    room_name: str,
    identity: str,
    external_turn: dict[str, Any] | None = None,
    key: str = "livekit-voice",
) -> dict[str, Any] | None:
    """Render the chat/voice session and return browser-originated turn events."""
    token = create_room_token(
        settings,
        room_name=room_name,
        identity=identity,
    )
    value = _voice_component(
        server_url=settings.url,
        token=token,
        room_name=room_name,
        identity=identity,
        local=settings.local,
        external_turn=external_turn,
        key=key,
        default=None,
    )
    return value if isinstance(value, dict) else None
