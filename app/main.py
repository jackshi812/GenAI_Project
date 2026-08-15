"""Streamlit interface for the voice-to-voice product discovery assistant."""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path

# Streamlit executes this file with app/ as the import root. Add the repository
# root before importing shared project modules.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st
from dotenv import load_dotenv

# Match the documented setup: credentials and mode settings live in the
# repository-root .env file. Existing shell variables keep precedence.
load_dotenv(REPO_ROOT / ".env")

from app.config import live_evidence_notice, product_live_notice, source_mode_label
from app.livekit_component import (
    live_voice,
    new_identity,
    new_room_name,
    settings_from_env,
)
from contracts import AssistantResult, ComparisonProduct, RagResult, StepEvent
from graph.build import run_graph
from graph.fast_reply import FastReply, build_fast_reply
from voice.stt import transcribe
from voice.tts import cap_for_speech, synthesize

DEFAULT_TRANSCRIPT = (
    "Compare the current price of the Nerf N Strike Elite Strongarm blaster "
    "with the catalog price."
)


def _money(value: float | str | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"${value:,.2f}"
    return value


def _render_product(
    product: ComparisonProduct, web_step: StepEvent | None = None
) -> None:
    conflicts = {conflict.field for conflict in product.conflicts}
    with st.container(border=True):
        image_column, catalog_column, live_column = st.columns([1, 2, 2])
        with image_column:
            if product.private is not None:
                st.image(product.private.image_url, width=80)
                st.caption("2020 catalog image")
            elif product.live is not None and product.live.image_url:
                st.image(product.live.image_url, width=80)
                st.caption("Live listing image")
            else:
                st.markdown("### 🌐")
                st.caption("Web result")
        with catalog_column:
            st.markdown("**Catalog (2020)**")
            if product.private is None:
                st.info("No reliable catalog match")
                st.caption("Showing current web products instead.")
            else:
                st.markdown(f"**{product.private.title}**")
                price = _money(product.private.price_low)
                if "price" in conflicts:
                    st.markdown(f":red[⚠ **Price: {price}**]")
                else:
                    st.markdown(f"**Price:** {price}")
                if product.private.budget_fit == "partial":
                    st.caption(f"Starting at {price} — some variants exceed budget")
                st.write(f"Brand: {product.private.brand or '—'}")
                st.caption("Rating: — · no ratings in the 2020 catalog")
                st.caption("Ingredients: not available in source data")
        with live_column:
            st.markdown("**Live**")
            if product.live is None:
                notice, detail = product_live_notice(web_step)
                if web_step is not None and web_step.status == "error":
                    st.warning(notice)
                else:
                    st.info(notice)
                st.caption(detail)
            else:
                if product.private is not None and product.live.image_url:
                    st.image(product.live.image_url, width=80)
                    st.caption("Live listing image")
                st.markdown(f"**{product.live.title}**")
                price = _money(product.live.price)
                if "price" in conflicts:
                    st.markdown(f":red[⚠ **Price: {price}**]")
                else:
                    st.markdown(f"**Price:** {price}")
                rating = (
                    f"{product.live.rating:.1f}"
                    if product.live.rating is not None
                    else "—"
                )
                st.write(f"Rating: {rating}")
                st.write(f"Availability: {product.live.availability or 'not reported'}")
                st.caption(product.live.snippet)

        for conflict in product.conflicts:
            conflict_line = (
                f":red[⚠ **{conflict.field.title()} conflict:** catalog "
                f"{_money(conflict.private_value)} vs live "
                f"{_money(conflict.live_value)} — {conflict.note}]"
            )
            st.markdown(conflict_line.replace("$", r"\$"))


def _render_evidence(result: AssistantResult, source_mode: str) -> None:
    st.subheader("Private catalog vs. live evidence")
    st.caption(source_mode)
    web_steps = [step for step in result.steps if step.tool == "web.search"]
    for index, product in enumerate(result.products[:3]):
        web_step = web_steps[index] if index < len(web_steps) else None
        _render_product(product, web_step)

    total_ms = sum(step.duration_ms or 0 for step in result.steps)
    completed_steps = sum(step.status == "completed" for step in result.steps)
    error_steps = sum(step.status == "error" for step in result.steps)
    status_summary = f"{completed_steps} completed"
    if error_steps:
        status_summary += f" · {error_steps} errors"
    with st.expander(
        f"Agent step log · {len(result.steps)} events · {status_summary} · {total_ms} ms",
        expanded=True,
    ):
        st.dataframe(
            [
                {
                    "node": step.node,
                    "tool": step.tool or "—",
                    "duration_ms": step.duration_ms,
                    "status": step.status,
                    "detail": step.detail,
                }
                for step in result.steps
            ],
            hide_index=True,
            width="stretch",
        )

    with st.expander("Citations", expanded=True):
        st.markdown("**🔒 Private catalog**")
        private_citations = [
            citation for citation in result.citations if citation.kind == "private"
        ]
        if not private_citations:
            st.caption("No reliable private catalog source for this result.")
        for citation in private_citations:
            st.markdown(f"- `private catalog` · `{citation.label}`")
        st.markdown("**🌐 Live sources**")
        live_citations = [item for item in result.citations if item.kind == "live"]
        if not live_citations:
            notice_kind, notice = live_evidence_notice(result)
            if notice_kind == "warning":
                st.warning(notice)
            else:
                st.caption(notice)
        for citation in live_citations:
            st.markdown(f"- `live` · [{citation.label}]({citation.url})")

    with st.expander("Match details", expanded=False):
        for product in result.products:
            if product.private is not None:
                title = product.private.title
            elif product.live is not None:
                title = product.live.title
            else:
                title = "Unknown product"
            st.markdown(f"**{title}**")
            if product.private is None:
                st.caption("Live-only fallback; no catalog comparison was possible.")
                continue
            if product.match is None:
                st.caption("No live match to evaluate.")
            else:
                st.write(
                    f"{product.match.similarity:.1%} similarity · "
                    f"{product.match.verdict}"
                )
                st.caption(product.match.reason)


def _render_pending_fast(data: dict) -> None:
    """Show fast catalog evidence while the full graph continues."""
    st.subheader("Product result")
    elapsed_ms = int(data.get("elapsed_ms") or 0)
    product_data = data.get("product")
    turn_kind = str(data.get("turn_kind") or "catalog")
    live_pending = bool(data.get("live_followup_needed"))

    if product_data:
        product = RagResult.model_validate(product_data)
        st.caption(f"2020 catalog match ready in {elapsed_ms} ms")
        with st.container(border=True):
            image_column, catalog_column, live_column = st.columns([1, 2, 2])
            with image_column:
                st.image(product.image_url, width=80)
            with catalog_column:
                st.markdown("**Catalog (2020)**")
                st.markdown(f"**{product.title}**")
                st.markdown(f"**Price:** {_money(product.price_low)}")
                st.write(f"Brand: {product.brand or '—'}")
                st.caption(f"Private document: {product.doc_id}")
            with live_column:
                st.markdown("**Live**")
                if live_pending:
                    st.info("Checking current products and prices…")
                    st.caption("Keep the conversation open while this finishes.")
                else:
                    st.caption("Web comparison was not needed for this request.")
        return

    if live_pending:
        st.info(
            "No reliable 2020 catalog match was found. Checking current web "
            "products instead…"
        )
    elif turn_kind == "conversation":
        st.caption("No product lookup was needed for this conversational turn.")
    else:
        st.warning("No reliable product match was found.")


st.set_page_config(page_title="Product Discovery Assistant", layout="wide")
st.markdown(
    """
    <style>
    div[data-testid="stAudioInput"] button {
        min-width: 4.5rem !important;
        min-height: 4.5rem !important;
        border-radius: 1rem !important;
        transform: scale(1.08);
        transform-origin: left center;
    }
    div[data-testid="stAudioInput"] {
        padding: 0.35rem 0 0.55rem;
    }
    div[data-testid="stTextInput"] input {
        min-height: 3.25rem;
        font-size: 1rem;
    }
    div[data-testid="stFormSubmitButton"] button {
        min-height: 3.1rem;
        font-size: 1rem;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Voice-to-Voice Product Discovery")
st.caption(
    "Speak or type to compare a private 2020 catalog with clearly labeled "
    "live evidence."
)

if "transcript" not in st.session_state:
    st.session_state.transcript = ""
if "audio_digest" not in st.session_state:
    st.session_state.audio_digest = None
if "answer_audio" not in st.session_state:
    st.session_state.answer_audio = None
if "answer_audio_text" not in st.session_state:
    st.session_state.answer_audio_text = None
if "assistant_result" not in st.session_state:
    st.session_state.assistant_result = None
if "fast_reply" not in st.session_state:
    st.session_state.fast_reply = None
if "pending_fast_reply" not in st.session_state:
    st.session_state.pending_fast_reply = None
if "livekit_room" not in st.session_state:
    st.session_state.livekit_room = new_room_name()
if "livekit_identity" not in st.session_state:
    st.session_state.livekit_identity = new_identity()

left, right = st.columns([1, 1.4])
new_transcript = False
with left:
    st.subheader("Talk or type to your store assistant")

    with st.container(border=True):
        st.markdown("#### Type a message")
        st.caption("Use the same grounded product search without turning on your mic.")
        with st.form("typed_message_form", clear_on_submit=True):
            typed_message = st.text_input(
                "Message",
                placeholder=(
                    "Ask for a product, budget, current price, or recommendation…"
                ),
                label_visibility="collapsed",
                key="typed_product_question",
            )
            typed_submitted = st.form_submit_button(
                "Send message",
                type="primary",
                use_container_width=True,
            )

    if typed_submitted:
        message = typed_message.strip()
        if message:
            st.session_state.transcript = message
            st.session_state.assistant_result = None
            st.session_state.pending_fast_reply = None
            st.session_state.answer_audio = None
            st.session_state.answer_audio_text = None
            st.session_state.fast_reply = None
            new_transcript = True
        else:
            st.warning("Type a message before sending.")

    st.markdown("#### Or speak live")
    try:
        live_event = live_voice(
            settings=settings_from_env(),
            room_name=st.session_state.livekit_room,
            identity=st.session_state.livekit_identity,
        )
    except Exception:
        live_event = None
        st.error("Live voice setup is incomplete. Check the LiveKit configuration.")

    if live_event:
        if live_event.get("type") == "fast_reply":
            fast_data = live_event.get("data") or {}
            st.session_state.pending_fast_reply = fast_data
            st.session_state.assistant_result = None
            st.session_state.transcript = str(fast_data.get("transcript") or "")
        elif live_event.get("type") == "assistant_result":
            try:
                live_result = AssistantResult.model_validate(live_event.get("data"))
                st.session_state.assistant_result = live_result
                st.session_state.pending_fast_reply = None
                st.session_state.transcript = live_result.transcript
                # Remote LiveKit audio is already played by the browser component.
                st.session_state.answer_audio = None
                st.session_state.answer_audio_text = None
                st.session_state.fast_reply = None
            except Exception:
                st.warning("The live session returned an invalid result payload.")

    with st.expander("Record and send instead", expanded=False):
        st.caption("Fallback mode: transcription begins only after recording stops.")
        recording = st.audio_input("Record a product question")
    if recording is not None:
        audio_bytes = recording.getvalue()
        digest = hashlib.sha256(audio_bytes).hexdigest()
        if digest != st.session_state.audio_digest:
            try:
                with st.spinner("Transcribing…"):
                    transcript = transcribe(audio_bytes, filename=recording.name)
                if transcript:
                    st.session_state.answer_audio = None
                    st.session_state.answer_audio_text = None
                    st.session_state.fast_reply = None
                    st.session_state.transcript = transcript
                    # Mark the recording as consumed as soon as ASR succeeds;
                    # a later graph or TTS error must not retranscribe it.
                    st.session_state.audio_digest = digest
                    new_transcript = True
                else:
                    st.warning("No speech was detected. Please record again.")
            except Exception:
                st.error("Speech-to-text failed. Please check the OpenAI setup and retry.")

    if new_transcript:
        try:
            with st.spinner("Finding a catalog match…"):
                fast_reply: FastReply = asyncio.run(
                    build_fast_reply(st.session_state.transcript)
                )
                st.session_state.fast_reply = fast_reply
                st.session_state.answer_audio = synthesize(
                    fast_reply.text,
                    model=os.getenv("FAST_TTS_MODEL", "tts-1"),
                )
                st.session_state.answer_audio_text = fast_reply.text

            # Streamlit sends these elements to the browser before the slower
            # graph call below completes, so speech can start while live search
            # and reconciliation continue.
            st.markdown("**Transcript**")
            st.write(st.session_state.transcript)
            st.markdown("**Assistant**")
            st.markdown(fast_reply.text.replace("$", r"\$"))
            if st.session_state.answer_audio:
                st.audio(
                    st.session_state.answer_audio,
                    format="audio/mp3",
                    autoplay=True,
                )
            if fast_reply.live_followup_needed:
                st.info("Checking today’s web listing and comparing sources…")
            else:
                st.info("Preparing the full product details…")
        except Exception:
            # Preserve the original full-graph path as a usable fallback.
            st.session_state.fast_reply = None
            st.session_state.answer_audio = None
            st.session_state.answer_audio_text = None
            st.warning("The quick spoken reply was unavailable; finishing the full search.")

previous_result = st.session_state.assistant_result
needs_result = (
    bool(st.session_state.transcript)
    and (
        previous_result is None
        or previous_result.transcript != st.session_state.transcript
    )
)
if needs_result:
    try:
        with st.spinner("Checking grounded product sources…"):
            graph_result = run_graph(st.session_state.transcript)
            spoken_answer = cap_for_speech(graph_result.answer_text)
            st.session_state.assistant_result = graph_result.model_copy(
                update={"answer_text": spoken_answer}
            )
    except Exception:
        st.error("Product discovery failed. Please check the graph and tool configuration.")
        new_transcript = False
        if previous_result is None:
            st.stop()
        st.session_state.transcript = previous_result.transcript

result: AssistantResult | None = st.session_state.assistant_result
if result is None:
    pending_fast = st.session_state.pending_fast_reply
    if pending_fast:
        with right:
            _render_pending_fast(pending_fast)
        st.stop()
    with left:
        st.info("Start the conversation, allow microphone access, and begin speaking.")
        st.caption(f'Try asking: “{DEFAULT_TRANSCRIPT}”')
    with right:
        st.subheader("What you’ll get")
        st.markdown("**Private catalog evidence** · prices from the 2020 dataset")
        st.markdown("**Web comparison** · clearly labeled live or recorded results")
        st.markdown("**Grounded answer** · conflicts, citations, and spoken playback")
    st.stop()

source_mode = source_mode_label(result)

if new_transcript and st.session_state.answer_audio is None:
    try:
        with st.spinner("Creating spoken answer…"):
            st.session_state.answer_audio = synthesize(result.answer_text)
            st.session_state.answer_audio_text = result.answer_text
    except Exception:
        st.error("Text-to-speech failed. The written answer is still available.")

with left:
    st.markdown("**Transcript**")
    st.write(result.transcript)
    st.caption(f"Source mode: {source_mode}")
    st.markdown("**Detailed answer**")
    st.markdown(result.answer_text.replace("$", r"\$"))
    if st.session_state.answer_audio:
        st.caption("Spoken answer")
        st.write(st.session_state.answer_audio_text)
        # A browser may block first autoplay; the visible player remains the replay control.
        st.audio(
            st.session_state.answer_audio,
            format="audio/mp3",
            autoplay=new_transcript and st.session_state.fast_reply is None,
        )

with right:
    _render_evidence(result, source_mode)
