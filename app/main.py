"""Streamlit interface for the voice-to-voice product discovery assistant."""

from __future__ import annotations

import base64
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

from app.config import (
    clarification_needed,
    live_evidence_notice,
    refinement_needed,
    source_mode_label,
)
from app.livekit_component import (
    live_voice,
    new_identity,
    new_room_name,
    settings_from_env,
)
from app.product_grid import (
    MAX_GRID_PRODUCTS,
    SHOPPING_GRID_CSS,
    comparison_rows,
    shopping_grid_html,
)
from contracts import AssistantResult
from graph.build import run_graph
from graph.fast_reply import (
    contextualize_followup,
    extract_budget_bounds,
)
from graph.preferences import clears_budget, is_contextual_followup_candidate
from graph.response_style import is_delegated_choice, is_rejection_followup
from voice.tts import cap_for_speech, synthesize

DEFAULT_TRANSCRIPT = (
    "Compare the current price of the Nerf N Strike Elite Strongarm blaster "
    "with the catalog price."
)


def _render_evidence(result: AssistantResult, source_mode: str) -> None:
    products = result.products[:MAX_GRID_PRODUCTS]
    refining = refinement_needed(result)
    st.subheader("Results")
    if source_mode != "Live MCP · Catalog only (web not requested)":
        st.caption(source_mode)
    if clarification_needed(result):
        st.info("Tell me a little more, and I’ll narrow this down before searching.")
        st.caption(
            'Try: “a toy under $20,” “a kitchen item,” or “a gift for a teenager.”'
        )
        return

    if refining:
        st.info(
            "These are your previous results. Tell me what you want changed, "
            "and I’ll search for better alternatives."
        )
    web_steps = [step for step in result.steps if step.tool == "web.search"]
    if products:
        st.markdown(
            shopping_grid_html(
                products,
                web_steps,
                top_recommendation=result.top_recommendation,
            ),
            unsafe_allow_html=True,
        )
    elif not refining:
        st.info("No grounded product results were found for this request.")

    with st.expander("Compare product details", expanded=False):
        if products:
            st.dataframe(
                comparison_rows(products),
                hide_index=True,
                width="stretch",
            )
            st.caption(
                "Ratings come only from web evidence. The catalog contains no "
                "ratings or ingredients."
            )
        else:
            st.caption("There are no products to compare for this turn.")

    total_ms = sum(step.duration_ms or 0 for step in result.steps)
    completed_steps = sum(step.status == "completed" for step in result.steps)
    error_steps = sum(step.status == "error" for step in result.steps)
    status_summary = f"{completed_steps} completed"
    if error_steps:
        status_summary += f" · {error_steps} errors"
    with st.expander(
        f"Agent step log · {len(result.steps)} events · {status_summary} · {total_ms} ms",
        expanded=False,
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

    with st.expander("Sources & citations", expanded=False):
        st.markdown("**Catalog**")
        private_citations = [
            citation for citation in result.citations if citation.kind == "private"
        ]
        if not private_citations:
            st.caption("No reliable private catalog source for this result.")
        for citation in private_citations:
            st.markdown(f"- `private catalog` · `{citation.label}`")
        st.markdown("**Web search**")
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
        for product in products:
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
    """Keep product imagery hidden until the canonical answer is presented."""
    st.subheader("Results")
    turn_kind = str(data.get("turn_kind") or "catalog")
    live_pending = bool(data.get("live_followup_needed"))
    st.info("Give me a moment while I pull up the best matches.")
    if live_pending:
        st.caption("Checking catalog and current product evidence…")
    elif turn_kind == "clarification":
        st.caption("Working out the most useful follow-up question…")
    elif turn_kind == "refinement":
        st.caption("Adjusting the recommendations around your feedback…")
    elif turn_kind == "conversation":
        st.caption("Preparing a response…")
    else:
        st.caption("Comparing the strongest grounded matches…")


st.set_page_config(page_title="Product Discovery Assistant", layout="wide")
st.markdown(
    f"""
    <style>
    .block-container {{
        max-width: 1600px;
        padding-top: 2.1rem;
    }}
    {SHOPPING_GRID_CSS}
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
    "pending_budget_max": None,
    "pending_budget_min": None,
    "active_budget_max": None,
    "active_budget_min": None,
    "last_shopping_result": None,
    "pending_refinement": False,
    "active_shopping_context": None,
    "last_assistant_answer": "",
    "awaiting_ui_commit": False,
    "causal_commit_supported": False,
}
for state_key, default_value in _SESSION_DEFAULTS.items():
    if state_key not in st.session_state:
        st.session_state[state_key] = default_value
if "livekit_room" not in st.session_state:
    st.session_state.livekit_room = new_room_name()
if "livekit_identity" not in st.session_state:
    st.session_state.livekit_identity = new_identity()

left, right = st.columns([0.9, 1.7], gap="large")
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
                current_result = st.session_state.assistant_result
                if (
                    current_result is not None
                    and current_result.products
                    and not refinement_needed(current_result)
                ):
                    st.session_state.last_shopping_result = current_result
                if current_result is not None:
                    st.session_state.last_assistant_answer = current_result.answer_text
                st.session_state.transcript = message
                st.session_state.assistant_result = None
                st.session_state.pending_fast_reply = None
                st.session_state.external_turn = None
                st.session_state.answer_audio = None
                st.session_state.answer_audio_text = None
                st.session_state.active_request_id = str(
                    typed_data.get("request_id") or event_id
                )
                st.session_state.input_source = "typed"
                st.session_state.awaiting_ui_commit = False
                st.session_state.causal_commit_supported = bool(
                    typed_data.get("supports_commit")
                )
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
        elif event_type == "turn_started":
            turn_data = live_event.get("data") or {}
            st.session_state.pending_fast_reply = turn_data
            st.session_state.assistant_result = None
            st.session_state.transcript = str(turn_data.get("transcript") or "")
            st.session_state.input_source = "voice"
            st.session_state.awaiting_ui_commit = False
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
                st.session_state.awaiting_ui_commit = False
                st.session_state.last_assistant_answer = live_result.answer_text
                parsed_min, parsed_max = extract_budget_bounds(live_result.transcript)
                if clears_budget(live_result.transcript):
                    st.session_state.active_budget_min = None
                    st.session_state.active_budget_max = None
                elif parsed_max is not None:
                    st.session_state.active_budget_min = parsed_min
                    st.session_state.active_budget_max = parsed_max
                if live_result.products and not refinement_needed(live_result):
                    st.session_state.last_shopping_result = live_result
                if live_result.shopping_context is not None:
                    st.session_state.active_shopping_context = (
                        live_result.shopping_context
                    )
                if clarification_needed(live_result) or refinement_needed(live_result):
                    if parsed_max is not None:
                        st.session_state.pending_budget_min = parsed_min
                        st.session_state.pending_budget_max = parsed_max
                    elif refinement_needed(live_result):
                        st.session_state.pending_budget_min = (
                            st.session_state.active_budget_min
                        )
                        st.session_state.pending_budget_max = (
                            st.session_state.active_budget_max
                        )
                else:
                    st.session_state.pending_budget_min = None
                    st.session_state.pending_budget_max = None
                st.session_state.pending_refinement = refinement_needed(live_result)
            except Exception:
                st.warning("The live session returned an invalid result payload.")
        elif event_type == "turn_committed":
            committed = live_event.get("data") or {}
            if str(committed.get("request_id") or "") == str(
                st.session_state.active_request_id or ""
            ):
                st.session_state.awaiting_ui_commit = False

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
        display_transcript = st.session_state.transcript
        feedback_turn = is_rejection_followup(display_transcript)
        delegated_turn = is_delegated_choice(display_transcript)
        contextual_turn = is_contextual_followup_candidate(
            display_transcript,
            st.session_state.active_shopping_context,
        )
        remembered_budget = (
            st.session_state.active_budget_max
            if feedback_turn or delegated_turn or contextual_turn
            else st.session_state.pending_budget_max
        )
        remembered_budget_min = (
            st.session_state.active_budget_min
            if feedback_turn or delegated_turn or contextual_turn
            else st.session_state.pending_budget_min
        )
        search_transcript = contextualize_followup(
            display_transcript,
            remembered_budget,
            remembered_budget_min,
        )
        prior_result = st.session_state.last_shopping_result
        dialogue_context = None
        if feedback_turn or delegated_turn or contextual_turn:
            dialogue_context = {
                "budget_max": st.session_state.active_budget_max,
                "budget_min": st.session_state.active_budget_min,
                "shopping_context": st.session_state.active_shopping_context,
                "products": list(prior_result.products) if prior_result else [],
                "citations": list(prior_result.citations) if prior_result else [],
                "previous_request": prior_result.transcript if prior_result else "",
                "previous_answer": st.session_state.last_assistant_answer,
                "rejected_previous": st.session_state.pending_refinement,
                "avoid_categories": sorted(
                    {
                        product.private.category
                        for product in (prior_result.products if prior_result else [])
                        if product.private is not None and product.private.category
                    }
                )
                if st.session_state.pending_refinement
                else [],
            }
        with st.spinner("Checking grounded product sources…"):
            if dialogue_context is None:
                graph_result = run_graph(search_transcript)
            else:
                graph_result = run_graph(
                    search_transcript,
                    dialogue_context=dialogue_context,
                )
            if graph_result.transcript != display_transcript:
                graph_result = graph_result.model_copy(
                    update={"transcript": display_transcript}
                )
            spoken_answer = cap_for_speech(graph_result.answer_text)
            st.session_state.assistant_result = graph_result.model_copy(
                update={"answer_text": spoken_answer}
            )
            parsed_min, parsed_max = extract_budget_bounds(search_transcript)
            if clears_budget(search_transcript):
                st.session_state.active_budget_min = None
                st.session_state.active_budget_max = None
            elif parsed_max is not None:
                st.session_state.active_budget_min = parsed_min
                st.session_state.active_budget_max = parsed_max
            if graph_result.products and not refinement_needed(graph_result):
                st.session_state.last_shopping_result = graph_result
            if graph_result.shopping_context is not None:
                st.session_state.active_shopping_context = (
                    graph_result.shopping_context
                )
            if clarification_needed(graph_result) or refinement_needed(graph_result):
                if parsed_max is not None:
                    st.session_state.pending_budget_min = parsed_min
                    st.session_state.pending_budget_max = parsed_max
                elif refinement_needed(graph_result):
                    st.session_state.pending_budget_min = (
                        st.session_state.active_budget_min
                    )
                    st.session_state.pending_budget_max = (
                        st.session_state.active_budget_max
                    )
            else:
                st.session_state.pending_budget_min = None
                st.session_state.pending_budget_max = None
            st.session_state.pending_refinement = refinement_needed(graph_result)
            st.session_state.last_assistant_answer = spoken_answer
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
            "audio_base64": (
                base64.b64encode(st.session_state.answer_audio).decode("ascii")
                if st.session_state.answer_audio
                else None
            ),
            "audio_mime": (
                "audio/mpeg" if st.session_state.answer_audio else None
            ),
        }
        st.session_state.awaiting_ui_commit = bool(
            st.session_state.causal_commit_supported
        )
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
        st.session_state.awaiting_ui_commit = bool(
            st.session_state.causal_commit_supported
        )
        st.session_state.transcript = ""
        sync_component = True

if sync_component:
    st.rerun()

result: AssistantResult | None = st.session_state.assistant_result
if result is not None and st.session_state.awaiting_ui_commit:
    with right:
        _render_pending_fast(
            {
                "turn_kind": "thinking",
                "live_followup_needed": False,
            }
        )
    st.stop()
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
