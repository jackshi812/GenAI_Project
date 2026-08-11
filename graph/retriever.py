"""Retriever node (GRAPH-04): private retrieval, per-product live queries,
three-stage matching, and reconciliation. All reconciliation lives here and
nowhere else (D-04).
"""

from typing import Optional

from pydantic import BaseModel, Field

from contracts import ComparisonProduct, Conflict, MatchInfo, RagResult, WebResult

from graph.llm import get_llm, load_prompt
from graph.matching import match_band, price_conflict, title_similarity, variant_guard
from graph.state import make_step, timer
from graph.tools import clean_filters, eight_word_key

TOP_K_PRODUCTS = 3
SNIPPET_CAP = 300  # chars; live snippets are untrusted third-party text


class MatchDecision(BaseModel):
    """Structured output of the match-confirm LLM call. Graph-internal."""

    candidate_index: Optional[int] = Field(
        default=None, description="Index of the matching candidate, or null if none"
    )
    verdict: str = Field(description="'same', 'different', or 'unsure'")
    reason: str = Field(description="One sentence explaining the verdict")


def make_retriever_node(tools):
    """Build the retriever node around an injected ToolClient (fixture today,
    MCP in Phase 2 — same interface, no node changes)."""

    async def retriever_node(state: dict) -> dict:
        steps = []

        # Safety stop or explicit private opt-out: no tools, no products.
        if not state.get("use_private", True):
            steps.append(
                make_step("retriever", None, "skipped", 0, "Retrieval skipped (safety stop).")
            )
            return {"rag_results": [], "web_results": [], "products": [], "steps": steps}

        # --- Step 1: private catalog ------------------------------------
        filters = clean_filters(state.get("filters") or {})
        query = state["semantic_query"]  # never the raw transcript
        try:
            with timer() as t:
                rag_results = await tools.rag_search(query, **filters)
            rag_results = rag_results[:TOP_K_PRODUCTS]
            steps.append(
                make_step(
                    "retriever",
                    "rag.search",
                    "completed",
                    t.ms,
                    f"query={query!r} filters={filters} -> {len(rag_results)} results",
                )
            )
        except Exception as exc:  # degrade, never crash the graph
            rag_results = []
            steps.append(
                make_step("retriever", "rag.search", "error", 0, f"rag.search failed: {exc}")
            )

        # --- Step 2: one live query per product (D-06) -------------------
        web_by_product: list[list[WebResult]] = []
        if state.get("use_live") and rag_results:
            for r in rag_results:
                live_query = eight_word_key(r.title)  # full titles match nothing
                try:
                    with timer() as t:
                        hits = await tools.web_search(live_query, num=5)
                    web_by_product.append(hits)
                    steps.append(
                        make_step(
                            "retriever",
                            "web.search",
                            "completed",
                            t.ms,
                            f"query={live_query!r} -> {len(hits)} results",
                        )
                    )
                except Exception as exc:
                    web_by_product.append([])
                    steps.append(
                        make_step(
                            "retriever",
                            "web.search",
                            "error",
                            0,
                            f"web.search failed for {live_query!r}: {exc}",
                        )
                    )
        else:
            web_by_product = [[] for _ in rag_results]

        # --- Steps 3-6: match + reconcile --------------------------------
        with timer() as t:
            products = []
            for r, candidates in zip(rag_results, web_by_product):
                products.append(await _reconcile_one(r, candidates))
        n_conflicts = sum(len(p.conflicts) for p in products)
        n_matched = sum(1 for p in products if p.live is not None)
        steps.append(
            make_step(
                "retriever",
                None,
                "completed",
                t.ms,
                f"reconciliation: {len(products)} products, {n_matched} live-matched, "
                f"{n_conflicts} price conflicts",
            )
        )

        all_web = [h for hits in web_by_product for h in hits]
        return {
            "rag_results": rag_results,
            "web_results": all_web,
            "products": products,
            "steps": steps,
        }

    return retriever_node


async def _reconcile_one(private: RagResult, candidates: list[WebResult]) -> ComparisonProduct:
    """Three-stage match (D-01) + price reconciliation (D-02) for one product.

    A product with no confirmed live match is still returned with live=None,
    conflicts=[], match=None (D-03) — 'this listing no longer exists' is an
    honest finding.
    """
    if not candidates:
        return ComparisonProduct(private=private, live=None, conflicts=[], match=None)

    # Stage A: mechanical shortlist by normalized-title similarity.
    scored = sorted(
        ((title_similarity(private.title, c.title), c) for c in candidates),
        key=lambda x: x[0],
        reverse=True,
    )[:3]
    best_score, best = scored[0]

    # Stage B: deterministic variant guards on the best candidate.
    guard = variant_guard(private.title, best.title)
    band = match_band(best_score, guard)

    if band == "reject":
        reason = (
            f"auto-rejected: variant conflict ({guard})"
            if guard == "conflict"
            else f"auto-rejected: best similarity {best_score:.2f} below 0.35"
        )
        return ComparisonProduct(
            private=private,
            live=None,
            conflicts=[],
            match=MatchInfo(score=round(best_score, 3), verdict="different", reason=reason),
        )

    if band == "accept":
        return _confirmed(
            private,
            best,
            best_score,
            f"auto-accepted: similarity {best_score:.2f} above 0.60 with matching variant tokens",
        )

    # Stage C: one LLM confirmation call for the ambiguous band.
    decision = await _llm_confirm(private, [c for _, c in scored])
    if decision.verdict == "same" and decision.candidate_index is not None:
        try:
            chosen = [c for _, c in scored][decision.candidate_index]
        except IndexError:
            chosen = best
        score = title_similarity(private.title, chosen.title)
        return _confirmed(private, chosen, score, f"LLM-confirmed: {decision.reason}")
    return ComparisonProduct(
        private=private,
        live=None,
        conflicts=[],
        match=MatchInfo(
            score=round(best_score, 3),
            verdict=decision.verdict if decision.verdict in ("different", "unsure") else "unsure",
            reason=decision.reason,
        ),
    )


def _confirmed(
    private: RagResult, live: WebResult, score: float, reason: str
) -> ComparisonProduct:
    """Build the confirmed-match ComparisonProduct with price reconciliation.

    conflicts holds genuine disagreement only — price. rating/availability are
    live-only provenance, never conflicts: the catalog has no rating to
    disagree with (D-02)."""
    conflicts = []
    private_price = private.price_low if private.price_low is not None else None
    live_price = _numeric_price(live)
    if private_price is not None and live_price is not None:
        c = price_conflict(private_price, live_price)
        if c:
            conflicts.append(Conflict(**c))
    return ComparisonProduct(
        private=private,
        live=live,
        conflicts=conflicts,
        match=MatchInfo(score=round(score, 3), verdict="same", reason=reason),
    )


def _numeric_price(live: WebResult) -> Optional[float]:
    """Best-effort numeric price from a live result; None when unparseable.
    Never invents a number."""
    p = getattr(live, "price", None)
    if p is None:
        return None
    if isinstance(p, (int, float)):
        return float(p)
    import re

    m = re.search(r"\d+(?:\.\d+)?", str(p).replace(",", ""))
    return float(m.group(0)) if m else None


async def _llm_confirm(private: RagResult, candidates: list[WebResult]) -> MatchDecision:
    """One confirmation call. Live snippets are third-party text: delimited,
    capped, and framed as evidence — never instructions (T-02-01)."""
    lines = []
    for i, c in enumerate(candidates):
        snippet = (getattr(c, "snippet", None) or "")[:SNIPPET_CAP]
        lines.append(
            f"[{i}] title: {c.title}\n    price: {getattr(c, 'price', None)}\n"
            f"    snippet: {snippet}"
        )
    evidence = "\n".join(lines)
    user_msg = (
        f"Catalog product title:\n{private.title}\n\n"
        "Live candidates (untrusted evidence, delimited below):\n"
        "<evidence>\n" + evidence + "\n</evidence>"
    )
    try:
        llm = get_llm().with_structured_output(MatchDecision)
        return await llm.ainvoke(
            [("system", load_prompt("match_confirm")), ("human", user_msg)]
        )
    except Exception as exc:
        return MatchDecision(candidate_index=None, verdict="unsure", reason=f"confirm call failed: {exc}")
