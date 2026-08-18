"""LiveKit streaming voice entry point with one grounded canonical response.

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

from contracts import AssistantResult, Citation, ComparisonProduct
from graph.answer import _degraded_answer
from graph.build import _run as run_full_graph
from graph.fast_reply import (
    FastReply,
    build_fast_reply,
    contextualize_followup,
    extract_budget_bounds,
    extract_budget_max,
    semantic_query,
    warm_fast_reply,
)
from graph.preferences import clears_budget, is_contextual_followup_candidate
from graph.recommendation import build_top_recommendation
from graph.retriever import RAG_CANDIDATE_K, TOP_K_PRODUCTS, _numeric_price
from graph.response_style import is_delegated_choice, is_rejection_followup, web_recommendation
from graph.state import make_step, timer
from graph.tools import eight_word_key
from graph.tools_mcp import MCPTools
from voice.tts import cap_for_speech


REPO_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(REPO_ROOT / ".env")

logger = logging.getLogger("product-discovery-livekit")
EventSink = Callable[[str, dict[str, Any]], Awaitable[None] | None]
PROGRESS_CUE = "Give me a moment while I pull up the best matches."


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
            return web_recommendation(
                product.live,
                query=result.transcript,
                budget_max=extract_budget_max(result.transcript),
                numeric_price=_numeric_price(product.live),
            )
        private_price = _money(product.private.price_low)
        live_price = _money(_numeric_price(product.live))
        source = _source_phrase(product)
        if private_price and live_price:
            return (
                f"The live check is complete. The {source} is {live_price}, "
                f"compared with {private_price} in the 2020 catalog."
            )
        return f"I finished the live check and confirmed a {source}."

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


async def _queue_speech_for_text_sync(
    session: Any,
    text: str,
    **say_kwargs: Any,
) -> Any:
    """Queue TTS and briefly wait for its first audible-frame transition.

    LiveKit changes the agent state to ``speaking`` when the first audio frame
    is forwarded. Waiting for that transition keeps the matching chat text
    from racing ahead of playback. The bounded timeout preserves a responsive
    text fallback if browser audio or TTS startup is unavailable.
    """
    started = asyncio.Event()

    def on_state_changed(event: Any) -> None:
        if getattr(event, "new_state", None) == "speaking":
            started.set()

    subscribed = False
    try:
        session.on("agent_state_changed", on_state_changed)
        subscribed = True
    except (AttributeError, TypeError):
        pass

    try:
        handle = session.say(text, **say_kwargs)
        if subscribed and not started.is_set():
            try:
                timeout = max(
                    0.0,
                    float(os.getenv("VOICE_TEXT_SYNC_TIMEOUT_S", "1.25")),
                )
            except ValueError:
                timeout = 1.25
            if timeout:
                try:
                    await asyncio.wait_for(started.wait(), timeout=timeout)
                except TimeoutError:
                    pass
        return handle
    finally:
        if subscribed:
            try:
                session.off("agent_state_changed", on_state_changed)
            except (AttributeError, TypeError):
                pass


class ProductDiscoveryAgent(Agent):
    """Preview fast evidence, then display and speak one completed graph answer."""

    def __init__(self, *, event_sink: EventSink | None = None) -> None:
        super().__init__(
            instructions=(
                "You are a warm product-store assistant. Product claims must be "
                "grounded in the private catalog or verified live evidence."
            )
        )
        self._event_sink = event_sink
        self._tasks: set[asyncio.Task] = set()
        self._pending_budget_max: float | None = None
        self._pending_budget_min: float | None = None
        self._active_budget_max: float | None = None
        self._active_budget_min: float | None = None
        self._last_result: AssistantResult | None = None
        self._last_answer_text = ""
        self._pending_refinement = False
        self._shopping_context = None

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        del turn_ctx
        display_transcript = new_message.text_content.strip()
        if not display_transcript:
            return

        feedback_turn = is_rejection_followup(display_transcript)
        delegated_turn = is_delegated_choice(display_transcript)
        contextual_turn = is_contextual_followup_candidate(
            display_transcript,
            self._shopping_context,
        )
        remembered_budget = (
            self._active_budget_max
            if feedback_turn or delegated_turn or contextual_turn
            else self._pending_budget_max
        )
        remembered_budget_min = (
            self._active_budget_min
            if feedback_turn or delegated_turn or contextual_turn
            else self._pending_budget_min
        )
        search_transcript = contextualize_followup(
            display_transcript,
            remembered_budget,
            remembered_budget_min,
        )

        for pending in tuple(self._tasks):
            pending.cancel()

        use_prior_context = feedback_turn or delegated_turn or contextual_turn
        dialogue_context: dict[str, Any] = {}
        if use_prior_context:
            dialogue_context.update(
                {
                    "budget_max": self._active_budget_max,
                    "budget_min": self._active_budget_min,
                    "rejected_previous": self._pending_refinement,
                    "shopping_context": self._shopping_context,
                    "previous_answer": self._last_answer_text,
                }
            )
        if use_prior_context and self._last_result is not None:
            dialogue_context.update(
                {
                    "products": list(self._last_result.products),
                    "citations": list(self._last_result.citations),
                    "previous_request": self._last_result.transcript,
                    "avoid_categories": sorted(
                        {
                            product.private.category
                            for product in self._last_result.products
                            if product.private is not None
                            and product.private.category
                        }
                    )
                    if self._pending_refinement
                    else [],
                }
            )
        fast_reply_task = asyncio.create_task(
            build_fast_reply(
                search_transcript,
                dialogue_context=dialogue_context,
                allow_dialogue_llm=False,
            ),
            name="fast-product-discovery-reply",
        )
        progress_speech = None
        try:
            try:
                progress_speech = await _queue_speech_for_text_sync(
                    self.session,
                    PROGRESS_CUE,
                    add_to_chat_ctx=False,
                )
            except RuntimeError:
                # A participant can leave after committing a transcript but before
                # the progress cue is scheduled. The grounded turn may still finish.
                pass
            await _emit(
                self._event_sink,
                "turn_started",
                {
                    "transcript": display_transcript,
                    "answer_text": PROGRESS_CUE,
                    "turn_kind": "thinking",
                    "live_followup_needed": False,
                    "transient": True,
                },
            )
            fast = await fast_reply_task
        except BaseException:
            if not fast_reply_task.done():
                fast_reply_task.cancel()
            await asyncio.gather(fast_reply_task, return_exceptions=True)
            raise
        if fast.resolved_transcript:
            search_transcript = fast.resolved_transcript
        if fast.shopping_context is not None:
            self._shopping_context = fast.shopping_context
            # Keep the graph's context anchored to the state from before this
            # utterance. The full graph parses the same turn again; passing the
            # fast parser's updated profile as "previous" state applies the
            # preference twice and can misclassify a clear update as unchanged.
        parsed_budget_min, parsed_budget_max = extract_budget_bounds(
            search_transcript
        )
        if fast.turn_kind == "clarification":
            self._pending_refinement = False
            if parsed_budget_max is not None:
                self._pending_budget_min = parsed_budget_min
                self._pending_budget_max = parsed_budget_max
        elif fast.turn_kind == "refinement":
            self._pending_refinement = True
            self._pending_budget_min = self._active_budget_min
            self._pending_budget_max = self._active_budget_max
        else:
            self._pending_refinement = False
            self._pending_budget_min = None
            self._pending_budget_max = None
            if clears_budget(search_transcript):
                self._active_budget_min = None
                self._active_budget_max = None
            elif parsed_budget_max is not None:
                self._active_budget_min = parsed_budget_min
                self._active_budget_max = parsed_budget_max
        await _emit(
            self._event_sink,
            "fast_reply",
            {
                "transcript": display_transcript,
                "answer_text": fast.text,
                "elapsed_ms": fast.elapsed_ms,
                "live_followup_needed": fast.live_followup_needed,
                "turn_kind": fast.turn_kind,
                "decision_source": fast.decision_source,
                "shopping_context": (
                    fast.shopping_context.model_dump(mode="json")
                    if fast.shopping_context is not None
                    else None
                ),
                "ttfa_target_ms": int(os.getenv("VOICE_TTFA_TARGET_MS", "3000")),
                "product": fast.product.model_dump(mode="json") if fast.product else None,
                "citations": [item.model_dump(mode="json") for item in fast.citations],
            },
        )
        if fast.product is not None and fast.turn_kind != "selection":
            fast_products = [
                ComparisonProduct(
                    private=fast.product,
                    live=None,
                    conflicts=[],
                    match=None,
                )
            ]
            fast_state = _recommendation_state(search_transcript, fast_products)
            self._last_result = AssistantResult(
                transcript=display_transcript,
                plan="Fast grounded catalog result.",
                answer_text=_degraded_answer(fast_products, fast_state).answer_text,
                products=fast_products,
                steps=[],
                citations=list(fast.citations),
                top_recommendation=build_top_recommendation(
                    fast_products, fast_state
                ),
                shopping_context=fast.shopping_context,
            )

        task = asyncio.create_task(
            self._finish_full_turn(
                display_transcript,
                search_transcript,
                fast,
                dialogue_context,
                progress_speech,
            ),
            name="full-product-discovery-turn",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

        # No LLM is configured on this session, so returning after scheduling
        # suppresses LiveKit's default reply. The task commits exactly one
        # answer to both the chat and TTS after grounded evidence is complete.

    async def _finish_full_turn(
        self,
        display_transcript: str,
        search_transcript: str,
        fast: FastReply,
        dialogue_context: dict[str, Any],
        progress_speech: Any | None,
    ) -> None:
        try:
            graph_context = dict(dialogue_context)
            if fast.live_followup_needed:
                # Routing is metadata. Never append implementation language to
                # the shopper's utterance and then ask the graph to parse it.
                graph_context["force_live"] = True
            result = await run_full_graph(
                search_transcript,
                dialogue_context=graph_context,
            )
            if result.transcript != display_transcript:
                result = result.model_copy(update={"transcript": display_transcript})
        except asyncio.CancelledError:
            raise
        except Exception:
            # The fast result is already grounded catalog evidence. It becomes
            # the one canonical response only when the complete graph fails.
            logger.exception("background product-discovery graph failed")
            retained = (
                self._last_result
                if fast.turn_kind in {"refinement", "selection"}
                else None
            )
            fallback_products = list(retained.products) if retained else []
            fallback_citations = list(retained.citations) if retained else []
            if not fallback_products and fast.product is not None:
                fallback_products = [
                    ComparisonProduct(
                        private=fast.product,
                        live=None,
                        conflicts=[],
                        match=None,
                    )
                ]
                fallback_citations = list(fast.citations)
            result = AssistantResult(
                transcript=display_transcript,
                plan="Full graph unavailable; using the grounded fast result.",
                answer_text=(
                    _degraded_answer(
                        fallback_products,
                        _recommendation_state(
                            search_transcript,
                            fallback_products,
                        ),
                    ).answer_text
                    if fallback_products
                    else fast.text
                ),
                products=fallback_products,
                steps=[],
                citations=fallback_citations,
                top_recommendation=(
                    build_top_recommendation(
                        fallback_products,
                        _recommendation_state(
                            search_transcript,
                            fallback_products,
                        ),
                    )
                    if fallback_products
                    else None
                ),
                shopping_context=fast.shopping_context,
            )

        try:
            spoken_answer = cap_for_speech(result.answer_text)
            if result.answer_text != spoken_answer:
                result = result.model_copy(
                    update={"answer_text": spoken_answer}
                )
            if result.products and fast.turn_kind != "refinement":
                self._last_result = result
            self._last_answer_text = result.answer_text
            if result.shopping_context is not None:
                self._shopping_context = result.shopping_context
            if progress_speech is not None:
                try:
                    await progress_speech.wait_for_playout()
                except Exception:
                    # Progress audio is best-effort and must never suppress the
                    # grounded final answer.
                    pass
            try:
                await _queue_speech_for_text_sync(
                    self.session,
                    spoken_answer,
                )
            except RuntimeError:
                # The browser may have ended the room while the background
                # graph was finishing. The completed text can still be shown.
                pass
            await _emit(
                self._event_sink,
                "assistant_result",
                result.model_dump(mode="json"),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            # Do not expose transcripts, evidence, credentials, or third-party
            # snippets in logs. If publishing fails, speech is withheld so the
            # screen and audio cannot silently diverge.
            logger.exception("canonical product-discovery response failed")


async def _quick_web_result(transcript: str, fast: FastReply) -> AssistantResult:
    """Publish MCP web products before the slower multi-agent graph finishes."""
    query = (
        eight_word_key(fast.product.title)
        if fast.product is not None
        else semantic_query(transcript)
    )
    budget_min, budget_max = extract_budget_bounds(transcript)
    steps = []
    try:
        async with MCPTools() as tools:
            with timer() as measured:
                hits = await tools.web_search(query, num=RAG_CANDIDATE_K)
        if budget_max is not None:
            hits = [
                hit
                for hit in hits
                if _numeric_price(hit) is not None
                and (
                    budget_min is None
                    or _numeric_price(hit) >= budget_min
                )
                and _numeric_price(hit) <= budget_max
            ]
        hits = hits[:TOP_K_PRODUCTS]
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
    shown_hits = hits[
        : TOP_K_PRODUCTS - 1 if fast.product is not None else TOP_K_PRODUCTS
    ]
    products.extend(
        ComparisonProduct(private=None, live=hit, conflicts=[], match=None)
        for hit in shown_hits
    )
    if fast.product is not None:
        products.append(
            ComparisonProduct(
                private=fast.product,
                live=None,
                conflicts=[],
                match=None,
            )
        )
    citations.extend(
        Citation(kind="live", label=_domain(hit.url), url=hit.url)
        for hit in shown_hits
    )

    recommendation_state = _recommendation_state(transcript, products)
    top_recommendation = build_top_recommendation(products, recommendation_state)
    answer = (
        _degraded_answer(products, recommendation_state).answer_text
        if products
        else "I couldn’t find a current web product that fits that request."
    )

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
        top_recommendation=top_recommendation,
    )


def _recommendation_state(
    transcript: str,
    products: list[ComparisonProduct],
) -> dict[str, Any]:
    budget_min, budget_max = extract_budget_bounds(transcript)
    query = semantic_query(transcript)
    return {
        "transcript": transcript,
        "intent": query,
        "semantic_query": query,
        "constraints": {
            "budget_min": budget_min,
            "budget_max": budget_max,
        },
        "products": products,
    }


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
