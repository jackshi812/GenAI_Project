---
status: resolved
trigger: "Can you add a top recommended item? The text suggests the $104 item but the first item is a different item. Also in the agent response include the match reason for the top recommended item please"
created: 2026-08-17
updated: 2026-08-17T16:57:00-05:00
diagnose_only: false
---

# Top recommendation mismatch

## Symptoms

- expected_behavior: The recommendation named in the assistant response should be the first, clearly marked Top recommendation card, and the response should explain why that item is the best match.
- actual_behavior: The response recommends a WANGE Taipei 101 set at $104.44, while the first displayed card is a different product, and the spoken text lacks a clear match rationale.
- error_messages: No runtime exception is shown.
- timeline: Observed after the conversation-intelligence fixes, in the latest LEGO search.
- reproduction: Ask for a LEGO toy between $50 and $100 and compare the assistant's named recommendation with the first product card.

## Current Focus

verification_decision:
  result: "End-to-end verification accepted; the original credentialed live workflow passes after restart."
  basis:
    - "Live trace forwarded query='LEGO toy', price_min=50, and price_max=100 and returned four in-range results."
    - "The assistant, products[0], and rendered top card all identified LEGO Gingerbread House at $99.99 with the same grounded reason."
    - "Rendered HTML contained exactly one Top recommendation badge, preserved first-card ordering, and excluded the former $104 mismatch."
    - "The health endpoint returned OK."
  remaining_blind_spot: "A visual browser click-through was unavailable because no browser was connected; exact credentialed trace and rendered-HTML verification cover every assertion in the documented reproduction, so this does not block resolution."
next_action: "None — the session is resolved, archived, and recorded in the debug knowledge base; no commit was created."

## Evidence

- timestamp: 2026-08-17T10:32:25-05:00
  observation: Screenshot shows the assistant naming WANGE Taipei 101 at $104.44 while the first product card is reported to be a different item.
  implication: Response/card presentation is not enforcing a shared top-recommendation identity.
- timestamp: 2026-08-17T15:31:57-05:00
  observation: Captured MCP trace called rag.search(query='lego toy between 50 100', category='Toys & Games', k=12) without price_min or price_max; the only per-product live lookup targeted the first RAG result, while answer prose selected a later $104.44 result and the grid retained retriever order.
  implication: Two coupled failures are directly observed: numeric range constraints are not reaching metadata filtering, and answer/grid top selection has no shared canonical identity.
- timestamp: 2026-08-17T15:36:00-05:00
  observation: No debug knowledge base exists to provide a known-pattern candidate. The worktree already contains broad modified and untracked graph/app files, including every likely implementation path for this bug.
  implication: The fix must be layered onto current concurrent/user edits and scoped narrowly; unrelated changes cannot be reverted or wholesale-rewritten.
- timestamp: 2026-08-17T15:48:00-05:00
  observation: Source trace shows `extract_budget_max` supports under/below/up-to prefixes and `$N`, but no range grammar; `interactive_router_node` hard-codes budget_min=None. The planner/retriever/MCP filter seam already forwards both numeric bounds when supplied.
  implication: The missing range is introduced at deterministic parsing/router state, not in the planner or MCP filter contract.
- timestamp: 2026-08-17T15:48:00-05:00
  observation: Retriever preference ranking establishes products[0], `_degraded_answer` also uses products[0], but `natural_answer_once` sends every product to the LLM and its gate accepts any subset of valid citations. `shopping_grid_html` renders list order and does not mark index 0 as Top recommendation.
  implication: The natural-answer acceptance path and UI presentation form a dual-source-of-truth/state-management bug; a later grounded candidate can become the prose pick without reordering the grid.
- timestamp: 2026-08-17T15:53:00-05:00
  observation: Read-only execution with the system Python failed during test collection because project dependencies `chromadb` and `langgraph` are absent from that interpreter; the UI-only grid baseline still passed.
  implication: Runtime import failure is an environment mismatch and does not test the hypotheses. Use the project's configured environment rather than changing application code or dependencies.
- timestamp: 2026-08-17T16:02:00-05:00
  observation: In `.venv`, the exact transcript returns `budget_max=None` and semantic_query='lego toy between 50 100'. Three focused existing baselines pass in the same runtime.
  implication: The range parsing failure is now directly reproduced in the configured project environment, while adjacent ranking, answer-grounding, and grid baselines are green before the fix.
- timestamp: 2026-08-17T16:08:00-05:00
  observation: Six focused RED regressions produced the predicted results: missing range API/metadata, acceptance of a later grounded candidate, missing TopRecommendation contract, unchanged selected-product order, and a polluted rag.search query with absent bounds.
  implication: Both root-cause mechanisms are confirmed and falsifiable. Implementation can proceed without altering planner/MCP arithmetic or inventing product facts.
- timestamp: 2026-08-17T16:32:00-05:00
  observation: Seven focused regressions now pass in `.venv`. The exact graph path sends query='lego toy', price_min=50.0, price_max=100.0; products[0], TopRecommendation.product_key, citations, answer title/reason, and first-card badge all identify the same grounded product.
  implication: The minimal fix addresses both confirmed mechanisms. Broader affected-module regression testing is required before requesting human verification.
- timestamp: 2026-08-17T16:50:00-05:00
  observation: All 77 tests in the six affected modules pass. Coverage includes app and voice preservation of both bounds, preliminary web-result ordering, stable prefixed identity keys, matched live-title/card alignment, natural non-fixed prose, exact grounded reason inclusion, and the 30-word speech cap.
  implication: Adjacent functionality is green; whole-repository discovery and final diff sanity remain before the human verification checkpoint.
- timestamp: 2026-08-17T16:55:00-05:00
  observation: Whole-repository unittest discovery passes 118/118, the affected-module suite passes 77/77, Python compilation succeeds, and scoped git diff whitespace validation reports no errors.
  implication: Automated verification is complete. Live MCP/UI confirmation in the user's real credentialed workflow is the remaining required checkpoint.
- timestamp: 2026-08-17T16:56:00-05:00
  observation: Tool-driven end-to-end verification reports that the exact credentialed live workflow passed after restart: query='LEGO toy' carried price_min=50 and price_max=100; all four results were in range; the assistant and first/top card both named LEGO Gingerbread House at $99.99 with the same grounded reason; rendered HTML had exactly one Top recommendation badge and no $104 result; health returned OK.
  implication: The original mismatch is resolved in the real provider-backed workflow. The unavailable visual browser click-through is a documented blind spot, but exact rendered-output verification exercises every assertion in the reproduction and does not require another checkpoint.

## Eliminated


## Resolution

- root_cause: The deterministic router/fast path had only upper-budget parsing and hard-coded budget_min=None, so range numbers polluted semantic retrieval instead of becoming numeric metadata filters. Independently, recommendation identity was duplicated: the LLM could select any grounded product, while the app rendered retriever order and the public result carried no canonical top metadata/reason.
- fix: Added numeric/spoken range parsing and semantic-clause removal; forwarded both existing numeric filter keys; added graph-owned TopRecommendation metadata with stable doc_id/URL identity and grounded reason; constrained prose to products[0], reordered explicit selections, rendered one first-card badge/reason, and preserved both bounds through app/voice follow-ups and preliminary web results.
- verification: Focused RED-to-GREEN regressions pass; affected modules pass 77/77; repository discovery passes 118/118; exact injected-tools reproduction forwards price_min=50 and price_max=100, keeps budget text out of semantic query, aligns prefixed canonical identity/title/reason with products[0], and caps answer at 30 words. Tool-driven end-to-end verification then confirmed the exact credentialed live workflow after restart: four in-range results, assistant/first-card alignment on LEGO Gingerbread House at $99.99, one rendered Top recommendation badge, the grounded reason present, no $104 result, and health OK.
- files_changed: [contracts.py, graph/state.py, graph/fast_reply.py, graph/nodes.py, graph/interactive.py, graph/answer.py, graph/recommendation.py, graph/build.py, app/product_grid.py, app/main.py, voice/livekit_agent.py, graph/test_fast_reply.py, graph/test_answer.py, graph/test_interactive.py, app/test_product_grid.py, app/test_main.py, voice/test_livekit_agent.py]
