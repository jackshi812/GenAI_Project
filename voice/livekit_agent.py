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
import re
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

from contracts import AssistantResult, Citation, ComparisonProduct
from graph.build import _run as run_full_graph
from graph.fast_reply import (
    FastReply,
    build_fast_reply,
    extract_budget_max,
    semantic_query,
    warm_fast_reply,
)
from graph.retriever import _numeric_price
from graph.state import make_step, timer
from graph.tools import eight_word_key
from graph.tools_mcp import MCPTools


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
        if product.private is None:
            live_price = _money(_numeric_price(product.live))
            price_phrase = f" at {live_price}" if live_price else ""
            return (
                f"I found {_short_title(product.live.title)} in current web "
                f"results{price_phrase}. The source is on screen."
            )
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

        for pending in tuple(self._tasks):
            pending.cancel()

        fast = await build_fast_reply(transcript)
        await _emit(
            self._event_sink,
            "fast_reply",
            {
                "transcript": transcript,
                "answer_text": fast.text,
                "elapsed_ms": fast.elapsed_ms,
                "live_followup_needed": fast.live_followup_needed,
                "turn_kind": fast.turn_kind,
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
            quick_web_emitted = False
            if fast.live_followup_needed:
                quick_result = await _quick_web_result(transcript, fast)
                await _emit(
                    self._event_sink,
                    "assistant_result",
                    quick_result.model_dump(mode="json"),
                )
                quick_followup = compose_live_followup(quick_result)
                if quick_followup:
                    quick_speech = asyncio.create_task(
                        self._speak_after(first_speech, quick_followup),
                        name="quick-web-followup-speech",
                    )
                    self._tasks.add(quick_speech)
                    quick_speech.add_done_callback(self._tasks.discard)
                quick_web_emitted = True

            if fast.turn_kind in {"conversation", "no_match"}:
                result = AssistantResult(
                    transcript=transcript,
                    plan=(
                        "Conversational response; no product tools needed."
                        if fast.turn_kind == "conversation"
                        else "No reliable catalog match; retrieval stopped."
                    ),
                    answer_text=fast.text,
                    products=[],
                    steps=[],
                    citations=[],
                )
            else:
                graph_transcript = transcript
                if fast.live_followup_needed and not re.search(
                    r"\b(?:current|today|now|latest|live|available|availability|rating|review)\b",
                    transcript,
                    re.IGNORECASE,
                ):
                    graph_transcript = (
                        f"{transcript} Compare current web price and availability."
                    )
                result = await run_full_graph(graph_transcript)
                if result.transcript != transcript:
                    result = result.model_copy(update={"transcript": transcript})
            if fast.turn_kind in {"conversation", "no_match"}:
                await first_speech.wait_for_playout()
            await _emit(
                self._event_sink,
                "assistant_result",
                result.model_dump(mode="json"),
            )
            followup = (
                compose_live_followup(result)
                if fast.live_followup_needed and not quick_web_emitted
                else None
            )
            if followup:
                await first_speech.wait_for_playout()
                try:
                    self.session.say(followup)
                except RuntimeError:
                    # The browser may have ended the room while the background
                    # graph was finishing. The completed result was still
                    # emitted when the participant remained connected.
                    return
        except asyncio.CancelledError:
            raise
        except Exception:
            # Do not expose transcripts, evidence, credentials, or third-party
            # snippets in logs. The fast grounded answer remains valid.
            logger.exception("background product-discovery graph failed")

    async def _speak_after(self, first_speech, text: str) -> None:
        try:
            await first_speech.wait_for_playout()
            self.session.say(text)
        except (asyncio.CancelledError, RuntimeError):
            return


def _short_title(title: str, limit: int = 8) -> str:
    return " ".join(str(title).split()[:limit]).rstrip(",.;:-")


async def _quick_web_result(transcript: str, fast: FastReply) -> AssistantResult:
    """Publish MCP web products before the slower multi-agent graph finishes."""
    query = (
        eight_word_key(fast.product.title)
        if fast.product is not None
        else semantic_query(transcript)
    )
    steps = []
    try:
        async with MCPTools() as tools:
            with timer() as measured:
                hits = await tools.web_search(query, num=5)
        budget_max = extract_budget_max(transcript)
        if budget_max is not None:
            hits = [
                hit
                for hit in hits
                if _numeric_price(hit) is not None
                and _numeric_price(hit) <= budget_max
            ]
        hits = hits[:3]
        steps.append(
            make_step(
                "retriever",
                "web.search",
                "completed",
                measured.ms,
                f"preliminary MCP query={query!r} -> {len(hits)} results",
                measured.started_at,
            )
        )
    except Exception as exc:
        hits = []
        steps.append(
            make_step(
                "retriever",
                "web.search",
                "error",
                0,
                f"preliminary MCP web search failed: {type(exc).__name__}",
            )
        )

    products = []
    citations = list(fast.citations)
    if fast.product is not None:
        products.append(
            ComparisonProduct(
                private=fast.product,
                live=None,
                conflicts=[],
                match=None,
            )
        )
    shown_hits = hits[: max(0, 3 - len(products))]
    products.extend(
        ComparisonProduct(private=None, live=hit, conflicts=[], match=None)
        for hit in shown_hits
    )
    citations.extend(
        Citation(kind="live", label=_domain(hit.url), url=hit.url)
        for hit in shown_hits
    )

    if shown_hits:
        price = _money(_numeric_price(shown_hits[0]))
        price_phrase = f" at {price}" if price else ""
        answer = (
            f"I found {_short_title(shown_hits[0].title)} in current web results"
            f"{price_phrase}."
        )
    elif fast.product is not None:
        answer = (
            "The catalog match is ready, but the preliminary web search did "
            "not return a current product."
        )
    else:
        answer = "I couldn’t find a current web product that fits that request."

    return AssistantResult(
        transcript=transcript,
        plan=(
            "Preliminary MCP web evidence; the full LangGraph comparison is "
            "continuing in the background."
        ),
        answer_text=answer,
        products=products,
        steps=steps,
        citations=citations,
    )


def _domain(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc or url


def create_session() -> AgentSession:
    """Configure the measured STT → fast retrieval → TTS pipeline."""
    vad = silero.VAD.load(
        min_speech_duration=0.08,
        min_silence_duration=float(os.getenv("VOICE_END_SILENCE_S", "0.55")),
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


def _prewarm_process(_process) -> None:
    warm_fast_reply()


server = AgentServer(num_idle_processes=1, setup_fnc=_prewarm_process)


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
