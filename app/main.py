"""Streamlit interface for the voice-to-voice product discovery assistant."""

from __future__ import annotations

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
    .block-container { padding-top: 2.4rem; }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Voice-to-Voice Product Discovery")
st.caption(
    "Speak or type to compare a private 2020 catalog with clearly labeled "
    "live evidence."
)

_SESSION_DEFAULTS = {
    "transcript": "",
    "answer_audio": None,
    "answer_audio_text": None,
    "assistant_result": None,
    "pending_fast_reply": None,
    "external_turn": None,
    "last_component_event_id": None,
    "active_request_id": None,
    "input_source": None,
}
for state_key, default_value in _SESSION_DEFAULTS.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = default_value
if "livekit_room" not in st.session_state:
    st.session_state.livekit_room = new_room_name()
if "livekit_identity" not in st.session_state:
    st.session_state.livekit_identity = new_identity()

left, right = st.columns([1, 1.4])
new_transcript = False
with left:
    st.subheader("Chat with your store assistant")
    try:
        live_event = live_voice(
            settings=settings_from_env(),
            room_name=st.session_state.livekit_room,
            identity=st.session_state.livekit_identity,
            external_turn=st.session_state.external_turn,
        )
    except Exception:
        live_event = None
        st.error("Live voice setup is incomplete. Check the LiveKit configuration.")

    event_id = str((live_event or {}).get("event_id") or "")
    is_new_event = bool(live_event) and (
        not event_id or event_id != st.session_state.last_component_event_id
    )
    if is_new_event:
        if event_id:
            st.session_state.last_component_event_id = event_id
        event_type = live_event.get("type")
        if event_type == "typed_message":
            typed_data = live_event.get("data") or {}
            message = str(typed_data.get("transcript") or "").strip()
            if message:
                st.session_state.transcript = message
                st.session_state.assistant_result = None
                st.session_state.pending_fast_reply = None
                st.session_state.answer_audio = None
                st.session_state.answer_audio_text = None
                st.session_state.active_request_id = str(
                    typed_data.get("request_id") or event_id
                )
                st.session_state.input_source = "typed"
                new_transcript = True
        elif event_type == "restart_chat":
            for state_key, default_value in _SESSION_DEFAULTS.items():
                st.session_state[state_key] = default_value
            st.session_state.livekit_room = new_room_name()
            st.session_state.livekit_identity = new_identity()
            st.rerun()
        elif event_type == "fast_reply":
            fast_data = live_event.get("data") or {}
            st.session_state.pending_fast_reply = fast_data
            st.session_state.assistant_result = None
            st.session_state.transcript = str(fast_data.get("transcript") or "")
            st.session_state.input_source = "voice"
        elif event_type == "assistant_result":
            try:
                live_result = AssistantResult.model_validate(live_event.get("data"))
                st.session_state.assistant_result = live_result
                st.session_state.pending_fast_reply = None
                st.session_state.transcript = live_result.transcript
                # Remote LiveKit audio is already played by the browser component.
                st.session_state.answer_audio = None
                st.session_state.answer_audio_text = None
                st.session_state.input_source = "voice"
            except Exception:
                st.warning("The live session returned an invalid result payload.")

previous_result = st.session_state.assistant_result
needs_result = (
    new_transcript
    and bool(st.session_state.transcript)
    and (
        previous_result is None
        or previous_result.transcript != st.session_state.transcript
    )
)
sync_component = False
if needs_result:
    try:
        with st.spinner("Checking grounded product sources…"):
            graph_result = run_graph(st.session_state.transcript)
            spoken_answer = cap_for_speech(graph_result.answer_text)
            st.session_state.assistant_result = graph_result.model_copy(
                update={"answer_text": spoken_answer}
            )
        try:
            st.session_state.answer_audio = synthesize(
                spoken_answer,
                model=os.getenv("FAST_TTS_MODEL", "tts-1"),
            )
            st.session_state.answer_audio_text = spoken_answer
        except Exception:
            st.session_state.answer_audio = None
            st.session_state.answer_audio_text = None
        st.session_state.external_turn = {
            "request_id": st.session_state.active_request_id,
            "transcript": st.session_state.transcript,
            "answer_text": spoken_answer,
        }
        sync_component = True
    except Exception:
        st.error("Product discovery failed. Please check the graph and tool configuration.")
        st.session_state.external_turn = {
            "request_id": st.session_state.active_request_id,
            "transcript": st.session_state.transcript,
            "answer_text": (
                "I’m sorry—I couldn’t finish that product search. "
                "Please try again in a moment."
            ),
        }
        st.session_state.transcript = ""
        sync_component = True

if sync_component:
    st.rerun()

result: AssistantResult | None = st.session_state.assistant_result
if result is None:
    pending_fast = st.session_state.pending_fast_reply
    if pending_fast:
        with right:
            _render_pending_fast(pending_fast)
        st.stop()
    with right:
        st.subheader("What you’ll get")
        st.markdown("**Private catalog evidence** · prices from the 2020 dataset")
        st.markdown("**Web comparison** · clearly labeled live or recorded results")
        st.markdown("**Grounded answer** · conflicts, citations, and spoken playback")
        st.caption(f'Try asking: “{DEFAULT_TRANSCRIPT}”')
    st.stop()

source_mode = source_mode_label(result)

with left:
    if st.session_state.answer_audio:
        with st.expander("Replay the latest spoken answer", expanded=False):
            st.audio(
                st.session_state.answer_audio,
                format="audio/mp3",
                autoplay=False,
            )

with right:
    _render_evidence(result, source_mode)
