"""LiveKit streaming voice entry point with a grounded fast-first response.

Run locally without LiveKit Cloud credentials:

    python -m voice.livekit_agent console

Use ``dev`` or ``start`` after configuring LIVEKIT_URL, LIVEKIT_API_KEY, and
LIVEKIT_API_SECRET. Interim transcripts are emitted by LiveKit automatically;
product evidence is published on the ``product.discovery`` data topic.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    MetricsCollectedEvent,
    TurnHandlingOptions,
    cli,
    metrics,
)
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.plugins import openai, silero

from contracts import AssistantResult, ComparisonProduct
from graph.build import _run as run_full_graph
from graph.fast_reply import FastReply, build_fast_reply
from graph.retriever import _numeric_price


REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

logger = logging.getLogger("product-discovery-livekit")
EventSink = Callable[[str, dict[str, Any]], Awaitable[None] | None]


def _money(value: float | str | None) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"${float(value):,.2f}"
    raw = str(value or "").strip()
    return raw or None


def _source_phrase(product: ComparisonProduct) -> str:
    if product.live is None:
        return "online result"
    if product.live.origin == "live_serper":
        return "current matched listing"
    if product.live.origin == "recorded_fixture":
        return "recorded web result"
    return "matched web result"


def compose_live_followup(result: AssistantResult) -> str | None:
    """Build a short, provenance-aware update after the full graph finishes."""
    for product in result.products:
        if product.live is None:
            continue
        private_price = _money(product.private.price_low)
        live_price = _money(_numeric_price(product.live))
        source = _source_phrase(product)
        if private_price and live_price:
            return (
                f"I finished checking. The {source} is {live_price}, compared with "
                f"{private_price} in the 2020 catalog. The sources are on screen."
            )
        return f"I finished checking and confirmed a {source}. The sources are on screen."

    web_steps = [step for step in result.steps if step.tool == "web.search"]
    if web_steps and any(step.status == "completed" for step in web_steps):
        return (
            "I finished checking, but I couldn’t confirm an exact online match. "
            "I kept the catalog result on screen."
        )
    if web_steps and any(step.status == "error" for step in web_steps):
        return (
            "The online check ran into trouble, so I kept the grounded catalog "
            "result on screen."
        )
    return None


async def _emit(sink: EventSink | None, event_type: str, data: dict[str, Any]) -> None:
    if sink is None:
        return
    outcome = sink(event_type, data)
    if inspect.isawaitable(outcome):
        await outcome


class ProductDiscoveryAgent(Agent):
    """Speak private evidence quickly, then finish the full graph in background."""

    def __init__(self, *, event_sink: EventSink | None = None) -> None:
        super().__init__(
            instructions=(
                "You are a warm product-store assistant. Product claims must be "
                "grounded in the private catalog or verified live evidence."
            )
        )
        self._event_sink = event_sink
        self._tasks: set[asyncio.Task] = set()

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        del turn_ctx
        transcript = new_message.text_content.strip()
        if not transcript:
            return

        fast = await build_fast_reply(transcript)
        await _emit(
            self._event_sink,
            "fast_reply",
            {
                "transcript": transcript,
                "answer_text": fast.text,
                "elapsed_ms": fast.elapsed_ms,
                "live_followup_needed": fast.live_followup_needed,
                "ttfa_target_ms": int(os.getenv("VOICE_TTFA_TARGET_MS", "3000")),
                "product": fast.product.model_dump(mode="json") if fast.product else None,
                "citations": [item.model_dump(mode="json") for item in fast.citations],
            },
        )

        first_speech = self.session.say(fast.text)
        task = asyncio.create_task(
            self._finish_full_turn(transcript, fast, first_speech),
            name="full-product-discovery-turn",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        # No LLM is configured on this session, so returning after scheduling
        # the grounded speech suppresses any second/default assistant reply.

    async def _finish_full_turn(self, transcript, fast: FastReply, first_speech) -> None:
        try:
            result = await run_full_graph(transcript)
            await _emit(
                self._event_sink,
                "assistant_result",
                result.model_dump(mode="json"),
            )
            followup = compose_live_followup(result) if fast.live_followup_needed else None
            if followup:
                await first_speech.wait_for_playout()
                self.session.say(followup)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Do not expose transcripts, evidence, credentials, or third-party
            # snippets in logs. The fast grounded answer remains valid.
            logger.exception("background product-discovery graph failed")


def create_session() -> AgentSession:
    """Configure the measured STT → fast retrieval → TTS pipeline."""
    vad = silero.VAD.load(
        min_speech_duration=0.08,
        min_silence_duration=float(os.getenv("VOICE_END_SILENCE_S", "0.35")),
        prefix_padding_duration=0.2,
    )
    return AgentSession(
        stt=openai.STT(
            model=os.getenv("LIVEKIT_STT_MODEL", "gpt-realtime-whisper"),
            use_realtime=True,
            vad=vad,
        ),
        vad=vad,
        turn_handling=TurnHandlingOptions(turn_detection="vad"),
        tts=openai.TTS(
            model=os.getenv("LIVEKIT_TTS_MODEL", "tts-1"),
            voice=os.getenv("LIVEKIT_TTS_VOICE", "alloy"),
        ),
    )


server = AgentServer()


@server.rtc_session(agent_name=os.getenv("LIVEKIT_AGENT_NAME", "product-discovery"))
async def entrypoint(ctx: JobContext) -> None:
    async def publish_event(event_type: str, data: dict[str, Any]) -> None:
        envelope = json.dumps(
            {"type": event_type, "data": data},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        await ctx.room.local_participant.publish_data(
            envelope,
            reliable=True,
            topic="product.discovery",
        )

    session = create_session()

    @session.on("metrics_collected")
    def on_metrics_collected(event: MetricsCollectedEvent) -> None:
        metrics.log_metrics(event.metrics)

    await session.start(
        agent=ProductDiscoveryAgent(event_sink=publish_event),
        room=ctx.room,
    )
    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
