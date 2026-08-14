"""Run the voice agent against LiveKit's documented local dev server defaults."""

from __future__ import annotations

import os


os.environ.setdefault("LIVEKIT_URL", "ws://127.0.0.1:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "secret")

from livekit.agents import cli  # noqa: E402

from voice.livekit_agent import server  # noqa: E402


if __name__ == "__main__":
    cli.run_app(server)
