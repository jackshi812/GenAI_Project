"""Streamlit interface for the voice-to-voice product discovery assistant."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

# Streamlit executes this file with app/ as the import root. Add the repository
# root before importing shared project modules.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from app.config import source_mode_label
from contracts import AssistantResult, ComparisonProduct
from graph.build import run_graph
from voice.stt import transcribe
from voice.tts import synthesize

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


def _render_product(product: ComparisonProduct) -> None:
    conflicts = {conflict.field for conflict in product.conflicts}
    with st.container(border=True):
        image_column, catalog_column, live_column = st.columns([1, 2, 2])
        with image_column:
            st.image(product.private.image_url, width=80)
        with catalog_column:
            st.markdown("**Catalog (2020)**")
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
                st.info("No live match found")
                st.caption("The 2020 listing may be delisted.")
            else:
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
    for product in result.products[:3]:
        _render_product(product)

    total_ms = sum(step.duration_ms or 0 for step in result.steps)
    with st.expander(
        f"Agent step log · {len(result.steps)} completed steps · {total_ms} ms",
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
        for citation in result.citations:
            if citation.kind == "private":
                st.markdown(f"- `private catalog` · `{citation.label}`")
        st.markdown("**🌐 Live sources**")
        live_citations = [item for item in result.citations if item.kind == "live"]
        if not live_citations:
            st.caption("No live source was needed for this result.")
        for citation in live_citations:
            st.markdown(f"- `live` · [{citation.label}]({citation.url})")

    with st.expander("Match details", expanded=False):
        for product in result.products:
            st.markdown(f"**{product.private.title}**")
            if product.match is None:
                st.caption("No live match to evaluate.")
            else:
                st.write(
                    f"{product.match.similarity:.1%} similarity · "
                    f"{product.match.verdict}"
                )
                st.caption(product.match.reason)


st.set_page_config(page_title="Product Discovery Assistant", layout="wide")
st.title("Voice-to-Voice Product Discovery")
st.caption("Compare a private 2020 catalog with clearly labeled live evidence.")

if "transcript" not in st.session_state:
    st.session_state.transcript = DEFAULT_TRANSCRIPT
if "audio_digest" not in st.session_state:
    st.session_state.audio_digest = None
if "answer_audio" not in st.session_state:
    st.session_state.answer_audio = None
if "assistant_result" not in st.session_state:
    st.session_state.assistant_result = None

left, right = st.columns([1, 1.4])
new_transcript = False
with left:
    st.subheader("Ask by voice")
    recording = st.audio_input("Ask for a product")
    if recording is not None:
        audio_bytes = recording.getvalue()
        digest = hashlib.sha256(audio_bytes).hexdigest()
        if digest != st.session_state.audio_digest:
            st.session_state.audio_digest = digest
            st.session_state.answer_audio = None
            try:
                with st.spinner("Transcribing…"):
                    transcript = transcribe(audio_bytes, filename=recording.name)
                if transcript:
                    st.session_state.transcript = transcript
                    new_transcript = True
                else:
                    st.warning("No speech was detected. Please record again.")
            except Exception:
                st.error("Speech-to-text failed. Please check the OpenAI setup and retry.")

previous_result = st.session_state.assistant_result
needs_result = (
    previous_result is None
    or previous_result.transcript != st.session_state.transcript
)
if needs_result:
    try:
        with st.spinner("Running the product discovery graph…"):
            st.session_state.assistant_result = run_graph(st.session_state.transcript)
    except Exception:
        st.error("Product discovery failed. Please check the graph and tool configuration.")
        new_transcript = False
        if previous_result is None:
            st.stop()
        st.session_state.transcript = previous_result.transcript

result: AssistantResult = st.session_state.assistant_result
source_mode = source_mode_label()

if new_transcript:
    try:
        with st.spinner("Creating spoken answer…"):
            st.session_state.answer_audio = synthesize(result.answer_text)
    except Exception:
        st.error("Text-to-speech failed. The written answer is still available.")

with left:
    st.markdown("**Transcript**")
    st.write(result.transcript)
    st.caption(f"Source mode: {source_mode}")
    st.markdown("**Answer**")
    st.markdown(result.answer_text.replace("$", r"\$"))
    if st.session_state.answer_audio:
        # A browser may block first autoplay; the visible player remains the replay control.
        st.audio(
            st.session_state.answer_audio,
            format="audio/mp3",
            autoplay=True,
        )

with right:
    _render_evidence(result, source_mode)
