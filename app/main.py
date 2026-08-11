"""Streamlit interface for the voice-to-voice product discovery assistant."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

# Streamlit executes this file with app/ as the import root. Add the repository
# root before importing shared project modules.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from contracts import (
    AssistantResult,
    Citation,
    ComparisonProduct,
    Conflict,
    MatchInfo,
    RagResult,
    StepEvent,
    WebResult,
)
from voice.stt import transcribe
from voice.tts import synthesize

FIXTURE_PATH = REPO_ROOT / "fixtures.json"
DEFAULT_TRANSCRIPT = (
    "Compare the current price of the Nerf N Strike Elite Strongarm blaster "
    "with the catalog price."
)


def _load_fixture_data() -> tuple[dict[str, RagResult], dict[str, list[WebResult]]]:
    raw = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    private = {
        item.doc_id: item
        for item in (RagResult.model_validate(row) for row in raw["rag_results"])
    }
    live = {
        query: [WebResult.model_validate(row) for row in rows]
        for query, rows in raw["web_results"].items()
    }
    return private, live


def load_result(transcript: str) -> AssistantResult:
    """Assemble a validated fixture result; Phase 2 replaces this seam."""
    private, live = _load_fixture_data()
    lowered = transcript.casefold()
    lego = private["AMZ-7E063675"]
    nerf = private["AMZ-7E4E86AE"]
    puzzles = [
        private["AMZ-C8BC973C"],
        private["AMZ-1AF647A8"],
        private["AMZ-6048F7ED"],
    ]

    if "nerf" in lowered or "strongarm" in lowered:
        nerf_live = live[nerf.title][0]
        products = [
            ComparisonProduct(
                private=nerf,
                live=nerf_live,
                conflicts=[
                    Conflict(
                        field="price",
                        private_value=nerf.price_low,
                        live_value=nerf_live.price,
                        note=(
                            "Recorded Serper price differs from the 2020 catalog; "
                            "the retailer URL is a search fallback."
                        ),
                    )
                ],
                match=MatchInfo(
                    similarity=0.638095,
                    verdict="same",
                    reason=(
                        "Auto-accepted above 0.60: the Nerf Strongarm model, rotating "
                        "barrel, and slam-fire variant evidence are compatible."
                    ),
                ),
            ),
            ComparisonProduct(private=lego, live=None, conflicts=[], match=None),
            ComparisonProduct(private=puzzles[0], live=None, conflicts=[], match=None),
        ]
        answer = (
            "The Nerf Strongarm was $13.99 in the 2020 catalog. Recorded eBay "
            "evidence shows $21.95 and a 3.5 rating, so the prices conflict."
        )
        plan = "Search the private catalog, add recorded live evidence, and reconcile price."
    elif "lego" in lowered or "10713" in lowered:
        lego_live = live[lego.title][0]
        products = [
            ComparisonProduct(
                private=lego,
                live=lego_live,
                conflicts=[
                    Conflict(
                        field="price",
                        private_value=lego.price_low,
                        live_value=lego_live.price,
                        note=(
                            "Recorded Serper price differs from the 2020 catalog; "
                            "confirm availability on the retailer search page."
                        ),
                    )
                ],
                match=MatchInfo(
                    similarity=0.666667,
                    verdict="same",
                    reason=(
                        "The live title is a shortened form of the Creative Suitcase "
                        "query, so the model and piece count need retailer verification."
                    ),
                ),
            ),
            ComparisonProduct(private=nerf, live=None, conflicts=[], match=None),
            ComparisonProduct(private=puzzles[0], live=None, conflicts=[], match=None),
        ]
        answer = (
            "The LEGO suitcase was $19.78 in the 2020 catalog. Recorded eBay "
            "evidence shows $12.95 and a 4.8 rating; verify current availability."
        )
        plan = "Find the catalog product, add recorded live evidence, and compare price."
    else:
        products = [
            ComparisonProduct(private=item, live=None, conflicts=[], match=None)
            for item in puzzles
        ]
        answer = (
            "The Buffalo Games Pokémon puzzle is $10.99 in the 2020 catalog and "
            "fits your $20 budget. The catalog has no rating data."
        )
        plan = "Use private semantic retrieval with a numeric $20 metadata filter."

    citations = [
        Citation(kind="private", label=product.private.doc_id, url=None)
        for product in products
    ]
    citations.extend(
        Citation(
            kind="live",
            label=(urlparse(product.live.url).hostname or "live source").removeprefix(
                "www."
            ),
            url=product.live.url,
        )
        for product in products
        if product.live is not None
    )
    return AssistantResult(
        transcript=transcript,
        plan=plan,
        answer_text=answer,
        products=products,
        steps=[
            StepEvent(
                node="fixture.load",
                tool=None,
                started_at="2026-08-11T00:00:00Z",
                duration_ms=1,
                status="completed",
                detail="Loaded recorded fixture evidence; no graph was run.",
            ),
            StepEvent(
                node="fixture.validate",
                tool=None,
                started_at="2026-08-11T00:00:00Z",
                duration_ms=1,
                status="completed",
                detail="Validated the screen data against the shared contract.",
            ),
        ],
        citations=citations,
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


def _render_evidence(result: AssistantResult) -> None:
    st.subheader("Private catalog vs. live evidence")
    st.caption("Fixture graph / recorded Serper data")
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

result = load_result(st.session_state.transcript)

if new_transcript:
    try:
        with st.spinner("Creating spoken answer…"):
            st.session_state.answer_audio = synthesize(result.answer_text)
    except Exception:
        st.error("Text-to-speech failed. The written answer is still available.")

with left:
    st.markdown("**Transcript**")
    st.write(result.transcript)
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
    _render_evidence(result)
