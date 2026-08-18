---
quick_id: 260817-fbc
status: ready
description: Make vague-product clarification replies ask directly without a failure preamble, and increase grounded product results from 6 to 9 while preserving latency and ordering.
phase: quick-260817-fbc
plan: 01
type: execute
wave: 1
depends_on: []
autonomous: true
files_modified:
  - graph/dialogue.py
  - prompts/dialogue.md
  - graph/test_dialogue.py
  - graph/retriever.py
  - graph/test_retriever.py
  - graph/test_interactive.py
  - voice/livekit_agent.py
  - voice/test_livekit_agent.py
  - app/product_grid.py
  - app/test_product_grid.py
  - app/test_main.py
must_haves:
  truths:
    - "A vague product request receives one direct clarifying question, without an apology or inability-to-understand/find/narrow preamble."
    - "A grounded turn can return and display up to 9 products in stable ranked order, with the canonical top recommendation still first."
    - "Retrieval still requests 12 candidates and increasing the display cap does not increase per-product live lookup count."
  artifacts:
    - path: "graph/dialogue.py"
      provides: "Deterministic validation and fallback for direct clarification wording"
    - path: "graph/retriever.py"
      provides: "Nine-result output cap separated from live-enrichment call limits"
    - path: "app/product_grid.py"
      provides: "Nine-card and nine-row presentation cap"
    - path: "voice/livekit_agent.py"
      provides: "Single-query preliminary result assembly capped at nine products"
  key_links:
    - from: "graph/dialogue.py"
      to: "graph/response_style.py"
      via: "invalid model clarification falls back to clarification_reply"
    - from: "graph/interactive.py"
      to: "graph/retriever.py"
      via: "planner requests RAG_CANDIDATE_K candidates; retriever stably slices the ranked result list"
    - from: "app/main.py"
      to: "app/product_grid.py"
      via: "MAX_GRID_PRODUCTS controls result slicing, cards, and comparison rows"
---

# Quick Task 260817-fbc Plan

<objective>
Make underspecified shopping turns ask their useful question immediately, then raise the grounded result surface from six to nine without changing evidence provenance, canonical ordering, or the number of latency-sensitive per-product live searches.

Purpose: Improve conversational confidence and comparison breadth while preserving the project's grounding and low-latency guarantees.
Output: Direct clarification validation, coordinated nine-result caps, and regression coverage across graph, voice, and app paths.
</objective>

<context>
@AGENTS.md
@.planning/STATE.md
@.planning/phases/01-parallel-build/01-CONTEXT.md
@graph/dialogue.py
@graph/response_style.py
@graph/retriever.py
@graph/interactive.py
@prompts/dialogue.md
@voice/livekit_agent.py
@app/product_grid.py
@app/main.py

<interfaces>
- `natural_dialogue_reply(kind, transcript, budget_max, ...)` accepts model text only through `_valid_dialogue`; `clarification_reply(...)` is the claim-free deterministic fallback.
- `RAG_CANDIDATE_K` is 12 and is passed through the interactive planner; `TOP_K_PRODUCTS` controls the graph result list.
- `_quick_web_result(transcript, fast)` performs one MCP search and assembles preliminary `ComparisonProduct` rows.
- `MAX_GRID_PRODUCTS` controls `app.main` slicing plus `shopping_grid_html(...)` and `comparison_rows(...)`.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Enforce question-first vague-product clarification</name>
  <files>graph/dialogue.py, prompts/dialogue.md, graph/test_dialogue.py</files>
  <behavior>
    - A valid question-first clarification from the dialogue model is accepted unchanged.
    - A clarification that starts with apology, failure, or inability language is rejected and replaced by the direct `clarification_reply` fallback, retaining the known budget and one question mark.
    - `no_match` dialogue may still honestly state that no reliable match was verified; the new rule is scoped only to vague-product clarification.
  </behavior>
  <action>Write the regression tests first. Make `_valid_dialogue` aware of the dialogue kind and require `clarification` output to lead directly into the useful question rather than narrating a failure to understand, find, or narrow the request. Keep the existing 30-word, single-question, allowed-number, and no-product-claim checks. Update `prompts/dialogue.md` with the same question-first contract so compliant model output is preferred, while retaining deterministic fallback enforcement when the model violates it. Do not weaken the truthful `no_match` behavior or the direct variants already supplied by `graph.response_style.clarification_reply`.</action>
  <verify>
    <automated>.venv/bin/python -m pytest -q graph/test_dialogue.py graph/test_response_style.py</automated>
  </verify>
  <done>Every vague-product clarification path emits one brief, claim-free, budget-preserving question without a failure preamble, and model violations fall back deterministically.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Return nine grounded products without adding live-search latency</name>
  <files>graph/retriever.py, graph/test_retriever.py, graph/test_interactive.py, voice/livekit_agent.py, voice/test_livekit_agent.py</files>
  <behavior>
    - Twelve ordered catalog candidates yield the first nine grounded products; product zero and its canonical recommendation identity remain unchanged.
    - Interactive live routing still performs at most one per-product web lookup, and non-interactive live enrichment performs no more per-product lookups than before this change.
    - Catalog and direct-web fallback paths cap returned products at nine while retaining source order and using one 12-candidate query for direct fallback.
    - Preliminary voice results contain at most nine products, reserve one slot for an existing fast catalog product when present, and use one MCP call rather than per-card calls.
  </behavior>
  <action>Write count, call-volume, and ordering regressions first. Raise the graph's returned-product limit to 9 while keeping `RAG_CANDIDATE_K` at 12. Separate the display/result limit from the existing live-enrichment limit so expanding the catalog slice cannot create three additional sequential product lookups; interactive mode must retain its one-query behavior, and the other graph mode must retain its pre-change maximum. Preserve stable ranked slicing and the `products[0]` canonical identity. Per D-03, leave catalog-only rows visible when no live match exists; per D-04, keep reconciliation in the Retriever; per D-06, do not issue live searches merely to populate additional cards. Align `_quick_web_result` with the 12-candidate/9-result constants, using one MCP request and at most eight web rows when a grounded fast catalog row occupies the ninth slot. Do not add ratings, prices, citations, or synthetic matches.</action>
  <verify>
    <automated>.venv/bin/python -m pytest -q graph/test_retriever.py graph/test_interactive.py voice/test_livekit_agent.py</automated>
  </verify>
  <done>All graph and preliminary voice result paths cap at nine, preserve the incoming rank and canonical first product, keep the candidate pool at twelve, and prove live lookup counts did not increase.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Display the same nine-product cap in cards and comparison rows</name>
  <files>app/product_grid.py, app/test_product_grid.py, app/test_main.py</files>
  <behavior>
    - Ten or more products render exactly nine cards and produce exactly nine comparison rows.
    - Fewer than nine products are all rendered without padding or fabricated rows.
    - Only the first card receives the canonical top badge and grounded reason; relative product order is unchanged.
    - The Streamlit result path retains nine products rather than truncating them earlier.
  </behavior>
  <action>Write the UI cap regressions first, then change `MAX_GRID_PRODUCTS` and its documentation to 9 so `app.main`, `shopping_grid_html`, and `comparison_rows` share the same bound. Update the existing Streamlit integration fixture from six to nine distinct products and assert nine survive into session state and rendered cards. Preserve the three-column responsive grid, source badges, explicit missing-field states, and first-card-only canonical recommendation per D-09, D-10, and D-14; do not reorder, duplicate, or backfill products in the presentation layer.</action>
  <verify>
    <automated>.venv/bin/python -m pytest -q app/test_product_grid.py app/test_main.py</automated>
  </verify>
  <done>The app consistently shows up to nine grounded products in original graph order across session state, cards, and comparison rows, with provenance and canonical-first treatment intact.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Dialogue model → graph | Model-generated prose is untrusted until deterministic dialogue validation accepts it. |
| Graph → MCP web search | Increasing visible results must not multiply latency-sensitive external calls or bypass returned evidence. |
| Graph result → app/voice | Ordered grounded products and canonical identity cross into two presentation surfaces. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-FBC-01 | Tampering | `graph/dialogue.py` | medium | mitigate | Kind-scoped validation rejects failure-prefaced clarification and retains existing claim/number bounds. |
| T-FBC-02 | Denial of Service | `graph/retriever.py` live enrichment | high | mitigate | Keep a separate pre-change per-product lookup ceiling and assert call counts while displaying nine catalog candidates. |
| T-FBC-03 | Tampering | graph → app/voice ordering | medium | mitigate | Stable slicing plus canonical-first regression tests; presentation code never reranks or fabricates rows. |
</threat_model>

<source_audit>

| Source | Item | Task | Status |
|--------|------|------|--------|
| QUICK GOAL | Direct clarification without failure preamble | 1 | COVERED |
| QUICK GOAL | Nine grounded results from twelve candidates | 2, 3 | COVERED |
| QUICK GOAL | Preserve latency and canonical ordering | 2, 3 | COVERED |
| CONTEXT | D-03/D-04/D-06 grounded rows, Retriever ownership, live-query discipline | 2 | COVERED |
| CONTEXT | D-09/D-10/D-14 contract and honest presentation boundaries | 3 | COVERED |
| REQ/RESEARCH | No quick-task-specific requirement IDs or research artifact supplied | — | N/A |

</source_audit>

<verification>
Run `.venv/bin/python -m pytest -q graph/test_dialogue.py graph/test_response_style.py graph/test_retriever.py graph/test_interactive.py voice/test_livekit_agent.py app/test_product_grid.py app/test_main.py`. Confirm the new tests explicitly assert 12 candidates, 9 returned/displayed products, unchanged lookup counts, stable first-nine ordering, and direct clarification wording.
</verification>

<success_criteria>
- Vague-product turns ask the useful question immediately and remain within the existing 30-word grounding guard.
- Graph, voice preview, Streamlit session state, card grid, and comparison table all enforce a nine-product maximum.
- The graph still retrieves 12 candidates, does not increase per-product live lookup volume, and leaves canonical product zero first.
- No price, rating, match, citation, or missing product row is invented.
</success_criteria>

<output>
Create `.planning/quick/260817-fbc-make-vague-product-clarification-replies/260817-fbc-SUMMARY.md` when done.
</output>
