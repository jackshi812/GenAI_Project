"""Retriever node (GRAPH-04): private retrieval, per-product live queries,
three-stage matching, and reconciliation. All reconciliation lives here and
nowhere else (D-04).
"""

from typing import Optional

from pydantic import BaseModel, Field

from contracts import ComparisonProduct, Conflict, MatchInfo, RagResult, WebResult

from graph.llm import get_llm, load_prompt
from graph.matching import match_band, price_conflict, title_similarity, variant_guard
from graph.relevance import catalog_result_is_relevant
from graph.state import make_step, timer
from graph.tools import clean_filters, eight_word_key

TOP_K_PRODUCTS = 3
SNIPPET_CAP = 300  # chars; live snippets are untrusted third-party text


class MatchDecision(BaseModel):
    """Structured output of the match-confirm LLM call. Graph-internal."""

    candidate_index: Optional[int] = Field(
        default=None,
        ge=0,
        description="Zero-based index of the matching candidate, or null if none",
    )
    verdict: str = Field(description="'same', 'different', or 'unsure'")
    reason: str = Field(description="One sentence explaining the verdict")


def make_retriever_node(tools, *, interactive: bool = False):
    """Build the retriever node around an injected ToolClient (fixture today,
    MCP in Phase 2 — same interface, no node changes)."""

    async def retriever_node(state: dict) -> dict:
        steps = []

        # Safety stop or explicit private opt-out: no tools, no products.
        if not state.get("use_private", True):
            reason = (
                "conversation"
                if state.get("turn_kind") == "conversation"
                else "safety stop"
            )
            steps.append(
                make_step(
                    "retriever",
                    None,
                    "skipped",
                    0,
                    f"Retrieval skipped ({reason}).",
                )
            )
            return {"rag_results": [], "web_results": [], "products": [], "steps": steps}

        # --- Step 1: private catalog ------------------------------------
        filters = clean_filters(state.get("filters") or {})
        query = state["semantic_query"]  # never the raw transcript
        try:
            with timer() as t:
                raw_rag_results = await tools.rag_search(query, **filters)
            rag_results = [
                result
                for result in raw_rag_results
                if catalog_result_is_relevant(query, result)
            ][:TOP_K_PRODUCTS]
            if interactive and state.get("use_live"):
                # One catalog candidate and one Serper request keep the
                # interactive graph bounded. Remaining slots may show honest
                # live-only alternatives from that same response.
                rag_results = rag_results[:1]
            steps.append(
                make_step(
                    "retriever",
                    "rag.search",
                    "completed",
                    t.ms,
                    f"query={query!r} filters={filters} -> {len(rag_results)} "
                    f"reliable of {len(raw_rag_results)} retrieved",
                    t.started_at,
                )
            )
        except Exception as exc:  # degrade, never crash the graph
            rag_results = []
            steps.append(
                make_step("retriever", "rag.search", "error", 0, f"rag.search failed: {exc}")
            )

        # No trustworthy private result: search the user's product phrase
        # directly instead of pretending a semantically nearby catalog item is
        # relevant. These rows are explicitly live-only in the UI/contract.
        if not rag_results:
            try:
                with timer() as t:
                    direct_hits = await tools.web_search(query, num=5)
                direct_hits = _filter_live_budget(direct_hits, filters)[:TOP_K_PRODUCTS]
                steps.append(
                    make_step(
                        "retriever",
                        "web.search",
                        "completed",
                        t.ms,
                        f"direct fallback query={query!r} -> {len(direct_hits)} results",
                        t.started_at,
                    )
                )
            except Exception as exc:
                direct_hits = []
                steps.append(
                    make_step(
                        "retriever",
                        "web.search",
                        "error",
                        0,
                        f"direct web fallback failed for {query!r}: {exc}",
                    )
                )
            products = [
                ComparisonProduct(
                    private=None,
                    live=hit,
                    conflicts=[],
                    match=None,
                )
                for hit in direct_hits
            ]
            steps.append(
                make_step(
                    "retriever",
                    None,
                    "completed",
                    0,
                    f"web-only fallback: {len(products)} products",
                )
            )
            return {
                "rag_results": [],
                "web_results": direct_hits,
                "products": products,
                "steps": steps,
            }

        # --- Step 2: one live query per product (D-06) -------------------
        web_by_product: list[list[WebResult]] = []
        if state.get("use_live") and rag_results:
            for index, r in enumerate(rag_results):
                if interactive and index >= 1:
                    web_by_product.append([])
                    continue
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
                            t.started_at,
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
                products.append(
                    await _reconcile_one(
                        r,
                        candidates,
                        allow_llm_confirmation=not interactive,
                    )
                )
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
                t.started_at,
            )
        )

        all_web = [h for hits in web_by_product for h in hits]
        if interactive:
            used_urls = {
                product.live.url for product in products if product.live is not None
            }
            for hit in all_web:
                if len(products) >= TOP_K_PRODUCTS:
                    break
                if hit.url in used_urls:
                    continue
                products.append(
                    ComparisonProduct(
                        private=None,
                        live=hit,
                        conflicts=[],
                        match=None,
                    )
                )
                used_urls.add(hit.url)
        return {
            "rag_results": rag_results,
            "web_results": all_web,
            "products": products,
            "steps": steps,
        }

    return retriever_node


def _filter_live_budget(
    results: list[WebResult], filters: dict
) -> list[WebResult]:
    """Apply numeric budgets to live-only fallback rows without guessing."""
    price_max = filters.get("price_max")
    price_min = filters.get("price_min")
    if price_max is None and price_min is None:
        return results
    kept = []
    for result in results:
        price = _numeric_price(result)
        if price is None:
            continue
        if price_max is not None and price > float(price_max):
            continue
        if price_min is not None and price < float(price_min):
            continue
        kept.append(result)
    return kept


async def _reconcile_one(
    private: RagResult,
    candidates: list[WebResult],
    *,
    allow_llm_confirmation: bool = True,
) -> ComparisonProduct:
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
    # Stage B: apply deterministic guards to every shortlisted candidate. A
    # conflicting top hit must not hide a valid lower-ranked hit, and candidates
    # with known pack/count/model/size/color conflicts must never reach the LLM.
    evaluated = [
        (score, candidate, guard, match_band(score, guard))
        for score, candidate in scored
        for guard in [variant_guard(private.title, candidate.title)]
    ]
    eligible = [item for item in evaluated if item[3] != "reject"]

    if not eligible:
        best_score, _, best_guard, _ = evaluated[0]
        reason = (
            "auto-rejected: all shortlisted candidates have deterministic "
            "variant conflicts"
            if all(guard == "conflict" for _, _, guard, _ in evaluated)
            else f"auto-rejected: no eligible candidate; best similarity {best_score:.2f}"
        )
        if best_guard == "conflict" and not all(
            guard == "conflict" for _, _, guard, _ in evaluated
        ):
            reason = (
                "auto-rejected: best candidate has a deterministic variant "
                "conflict and remaining candidates are below similarity threshold"
            )
        return ComparisonProduct(
            private=private,
            live=None,
            conflicts=[],
            match=MatchInfo(similarity=round(best_score, 3), verdict="different", reason=reason),
        )

    best_score, best, _, best_band = eligible[0]

    if best_band == "accept":
        return _confirmed(
            private,
            best,
            best_score,
            f"auto-accepted: similarity {best_score:.2f} above 0.60 with matching variant tokens",
        )

    if not allow_llm_confirmation:
        return ComparisonProduct(
            private=private,
            live=None,
            conflicts=[],
            match=MatchInfo(
                similarity=round(best_score, 3),
                verdict="unsure",
                reason=(
                    "Interactive deterministic check could not confirm the "
                    "variant; candidate is shown separately as live evidence."
                ),
            ),
        )

    # Stage C: one LLM confirmation call for the ambiguous candidates only.
    llm_candidates = [candidate for _, candidate, _, _ in eligible]
    decision = await _llm_confirm(private, llm_candidates)
    if decision.verdict == "same" and decision.candidate_index is not None:
        if decision.candidate_index >= len(eligible):
            return ComparisonProduct(
                private=private,
                live=None,
                conflicts=[],
                match=MatchInfo(
                    similarity=round(best_score, 3),
                    verdict="unsure",
                    reason="LLM returned an invalid candidate index; no match accepted",
                ),
            )

        score, chosen, _, _ = eligible[decision.candidate_index]
        # Defense in depth: deterministic variant conflicts cannot be overridden
        # by an LLM decision, even if candidate data changes during confirmation.
        chosen_guard = variant_guard(private.title, chosen.title)
        if chosen_guard == "conflict":
            return ComparisonProduct(
                private=private,
                live=None,
                conflicts=[],
                match=MatchInfo(
                    similarity=round(score, 3),
                    verdict="different",
                    reason="LLM selection rejected by deterministic variant guard",
                ),
            )
        return _confirmed(private, chosen, score, f"LLM-confirmed: {decision.reason}")
    return ComparisonProduct(
        private=private,
        live=None,
        conflicts=[],
        match=MatchInfo(
            similarity=round(best_score, 3),
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
            moved = "rose" if c["direction"] == "up" else "dropped"
            conflicts.append(
                Conflict(
                    field="price",
                    private_value=c["private_value"],
                    live_value=c["live_value"],
                    note=(
                        f"price {moved} from ${c['private_value']:.2f} (2020 catalog) "
                        f"to ${c['live_value']:.2f} (live)"
                    ),
                )
            )
    return ComparisonProduct(
        private=private,
        live=live,
        conflicts=conflicts,
        match=MatchInfo(similarity=round(score, 3), verdict="same", reason=reason),
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
