---
status: awaiting_human_verify
trigger: "The latest transcript asks for a backpack that is not black, but the agent cannot understand the negative preference."
created: 2026-08-17
updated: 2026-08-17T21:25:14Z
diagnose_only: false
---

# Preserve product context for negative preferences

## Symptoms

- expected_behavior: A request for a backpack that is not black should search for backpacks, exclude products whose grounded title/details are black, retain the backpack context across follow-ups such as "I don't want black," and explain a positively grounded non-black recommendation.
- actual_behavior: The latest conversation first searched for `backpack`, selected a black Everest backpack, then converted the follow-up into a new search for `don't want`, losing both the backpack context and the actionable black exclusion.
- error_messages: No runtime exception is shown.
- timeline: Observed in the latest live conversation after multi-turn preference handling was added.
- reproduction: Ask for a backpack, then say "I don't want black" or "not black." Also test one-turn forms such as "a backpack that's not black" and contextual updates such as "I want it to be pink."

## Current Focus

- hypothesis: The confirmed parser and pre-cap filtering fixes resolve the negative-preference context loss and six-card underfill without weakening grounding, latency, or response-identity contracts.
- test: Human verification in the real voice/UI workflow using one-turn and follow-up negative-color requests.
- expecting: MCP/step evidence searches `backpack` rather than `don't want`, black evidence is absent, six eligible cards appear when available, and displayed/spoken top recommendation identities match.
- next_action: Ask the user to repeat the real backpack workflow and confirm the observed text, audio, query, and product cards.
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- timestamp: 2026-08-17T21:05:09Z
  observation: MCP log records `rag.search` with query `backpack`; live comparison then searches the black `Everest Deluxe Small Backpack, Black, One Size`.
  implication: The active shopping product was a backpack and the shown top result was black.
- timestamp: 2026-08-17T21:05:32Z
  observation: The next MCP call searches `don't want` instead of `backpack`, followed by an unrelated web result.
  implication: The negative follow-up was misclassified as a new product query before retrieval.
- timestamp: 2026-08-17
  observation: Direct parsing with prior `ShoppingContext(product_query='backpack')` yields `product_query="don't want"`, `excluded=['black']`, `resolved_query="don't want"`, and `is_followup=False` for `I don't want black`.
  implication: Exclusion extraction works, but context classification/query composition drops the product family.
- timestamp: 2026-08-17
  observation: Trace inspection found `is_new_product_request()` removes the color facet but leaves contraction/negation scaffolding (`don`, `t`, or `not`); its final `bool(meaningful)` branch then incorrectly resets the active product context.
  implication: Negative facet-only updates must be classified as contextual unless a genuine novel product family remains after facet and grammar removal.
- timestamp: 2026-08-17
  observation: `I want it to be pink` matches `_NEW_SEARCH_CUE` before the contextual-pronoun check, while `That's right` is absent from the acknowledgement pattern.
  implication: Positive pronoun refinements and confirmations can incorrectly launch new product/web searches even though they should retain context or terminate the turn without retrieval.
- timestamp: 2026-08-17
  observation: Existing downstream private and live filters hard-remove products whose grounded title/features or title/snippet contain an excluded color; `best_available_facet_pool` does not relax exclusions when no survivors remain.
  implication: The exclusion enforcement is grounded and fail-closed; the fix should preserve it and focus on parsing/classification/query composition.
- timestamp: 2026-08-17T21:12:40Z
  observation: The debug knowledge base contains only `top-recommendation-mismatch`; it has no two-keyword overlap with the negative-preference symptom.
  implication: There is no known-pattern root-cause candidate to prioritize, though top-recommendation/text identity remains a required regression boundary.
- timestamp: 2026-08-17T21:12:40Z
  observation: Project skill discovery found no repository-local `SKILL.md` files under `.codex/skills` or `.agents/skills`.
  implication: No additional project skill rules apply beyond `AGENTS.md`, `Instructions.md`, and the GSD debugger protocol.
- timestamp: 2026-08-17T21:14:00Z
  observation: The worktree contains extensive pre-existing modified and untracked implementation work across app, graph, voice, catalog, MCP, and planning files; `graph/preferences.py` and its test file are untracked.
  implication: The fix must be a narrow in-place edit, preserve all surrounding work, and must not stage, commit, regenerate, or revert unrelated files.
- timestamp: 2026-08-17T21:14:00Z
  observation: Both `graph/nodes.py` and `graph/fast_reply.py` import the shared `resolve_preferences` path.
  implication: A minimal correction in preference resolution can align the low-latency fast reply and authoritative LangGraph route while preserving their existing latency/audio contracts.
- timestamp: 2026-08-17T21:16:00Z
  observation: `_rule_resolution` computes facet updates, strips them from the semantic query, and then calls `is_new_product_request`; an `explicit_new=True` result creates a fresh `ShoppingContext` before exclusions are applied.
  implication: Misclassification directly explains why `I don't want black` becomes a new family such as `don't want` even though `black` is correctly stored in `excluded`.
- timestamp: 2026-08-17T21:16:00Z
  observation: `_NEW_SEARCH_CUE` is checked before `_CONTEXT_PRONOUNS`, while the acknowledgement pattern covers `yes/yeah/...` but not `that's right`.
  implication: The same ordering can independently reset pronoun refinements, and acknowledgement vocabulary has a coverage gap that can launch retrieval instead of ending the turn conversationally.
- timestamp: 2026-08-17T21:18:00Z
  observation: The first parser-matrix driver failed at Python parse time because a compound `async def` statement followed a semicolon; it did not execute project code. Independently, the existing `graph.test_preferences` and `graph.test_fast_reply` suites ran 44 tests successfully.
  implication: The matrix needs a corrected driver, and current tests do not cover the reported negative-context regression.
- timestamp: 2026-08-17T21:20:00Z
  observation: The corrected matrix reproduced every reported divergence: one-turn resolved to `backpack that's`; negative follow-ups resolved to `don't want` or `product`; the pink pronoun update resolved to `it be pink`; and `That's right` resolved as a new product. Bare/cued laptop switches remained correct.
  implication: The root mechanism is directly reproducible in deterministic preference parsing and is not dependent on an LLM, MCP, retrieval, audio, or UI timing.
- timestamp: 2026-08-17T21:17:22Z
  observation: Five focused parser assertions are RED on the unmodified implementation, while the focused assertion that excluded `black` removes both private-title and live-title/snippet evidence already passes.
  implication: The regression is isolated upstream of retrieval; the new tests precisely reproduce it and downstream exclusion enforcement is not the cause.
- timestamp: 2026-08-17T21:19:00Z
  observation: After the minimal parser patch, all five focused tests pass, including the one-turn/multi-turn matrix, explicit suitcase switch, and private/live exclusion assertion.
  implication: The counterfactual change fixes the directly reproduced mechanism without a phrase-specific backpack/black branch.
- timestamp: 2026-08-17T21:23:00Z
  observation: The exact full-graph regression queries `backpack` and preserves `excluded=['black']`, but returns five products when a black candidate ranks first ahead of six valid nonblack candidates.
  implication: Parser and exclusion behavior are correct, but candidate slicing occurs before exclusion filtering and underfills the required six-card grid.
- timestamp: 2026-08-17T21:25:00Z
  observation: Private retrieval slices reliable RAG results to six before any preference filter, and direct live fallback slices budget-filtered hits to six before wrapping/filtering/ranking them.
  implication: Both grounded source paths share the same filter-after-cap ordering defect; selecting from lightweight wrappers first fixes coverage without reconciling or enriching all twelve candidates.
- timestamp: 2026-08-17T21:29:00Z
  observation: After pre-filtering/ranking lightweight candidates before the cap, the private full-graph black-first regression and all three retriever limit/direct-live tests pass; private live-lookups remain capped at six.
  implication: Six eligible cards are restored for both source paths without reconciling all twelve or relaxing exclusions.
- timestamp: 2026-08-17T21:29:00Z
  observation: Exact one-turn and multi-turn fast replies both call catalog search with query `backpack`, select `Pink Canvas Travel Backpack` over a black Everest result, and preserve `excluded=['black']`; the follow-up is classified `preference_update`.
  implication: The low-latency path shares the corrected parser and grounded exclusion behavior without added LLM or network work.
- timestamp: 2026-08-17T21:32:00Z
  observation: The dedicated private retriever regression passes: black-first plus six nonblack RAG candidates returns all six nonblack products, keeps `rag_results` aligned, and performs exactly six live lookups.
  implication: Pre-filtering restores card count while preserving the existing latency/enrichment ceiling and canonical ranked order.
- timestamp: 2026-08-17T21:36:00Z
  observation: The nine-module targeted suite ran 124 tests successfully across preference parsing, fast reply, retriever, interactive graph, answer/recommendation, TTS, grid, LiveKit, and Streamlit app boundaries.
  implication: The fixes preserve current grounding, recommendation identity, audio-text identity, six-card rendering, and adjacent conversation behavior.
- timestamp: 2026-08-17T21:41:00Z
  observation: The new voice boundary test observed `run_full_graph('Find backpack', ...)`, not the raw `I don't want black`; its only failure was an assertion expecting the raw display transcript.
  implication: The production voice boundary already forwards the corrected resolved backpack search as intended; the regression should assert that canonical handoff explicitly.
- timestamp: 2026-08-17T21:43:00Z
  observation: The corrected voice boundary and LLM-enabled `That's right` acknowledgement tests both pass.
  implication: Persisted backpack context reaches both fast and full voice paths, the graph receives `Find backpack` rather than `don't want`, active context updates to exclude black, and confirmations avoid an unnecessary preference-model call.
- timestamp: 2026-08-17T21:25:14Z
  observation: Final targeted verification ran 125 tests successfully across parser, fast reply, private/direct-live retrieval, interactive graph, answer/recommendation, exact TTS input, six-card grid, LiveKit persistence, and Streamlit propagation.
  implication: All requested automated acceptance boundaries pass together after the fixes.
- timestamp: 2026-08-17T21:25:14Z
  observation: Scoped diff checking reports no whitespace errors, no files were staged or committed, and implementation changes use general grammar/exclusion logic rather than a product/color-specific branch.
  implication: The patch is clean, minimally scoped to the confirmed mechanisms, and preserves the user's unrelated dirty worktree changes.

## Eliminated

- hypothesis: Private or live retrieval filtering ignores the excluded color and allows black products to survive.
  evidence: A focused test passes with both a black private catalog title and black live title/snippet removed while a pink private backpack survives.
  timestamp: 2026-08-17T21:17:22Z

## Resolution

- root_cause: `is_new_product_request` treated contraction/negation/auxiliary residue (`don`, `t`, `not`, `it`, `be`) as evidence of a novel product after removing known facets, and it evaluated `I want ...` before contextual pronouns. Separately, `_strip_facets` left negation grammar in semantic product queries. After parsing was fixed, both private and direct-live retriever branches capped candidates at six before strict preference exclusions, so removing a black top result underfilled the six-card grid.
- fix: Added general novelty grammar and negated-phrase subtraction, recognized explicit confirmations, and conditionally removed negation/contrast scaffolding after grounded exclusions are stripped. Moved existing preference filtering/ranking ahead of the six-item cap for lightweight private and direct-live candidate pools, while preserving six-item enrichment/reconciliation limits and aligned evidence. Added focused parser, graph, and direct-live regressions.
- verification: Focused RED reproduced five parser failures. GREEN verified exact one/multi-turn parsing, true suitcase switch, private/live exclusions, fast `backpack` queries, six nonblack full-graph products, six private live-lookups, aligned six-row direct-live fallback, canonical top/answer identity, exact TTS text, persisted voice context, and six-card UI rendering. Final targeted suite: 125 tests passed.
- files_changed: [graph/preferences.py, graph/retriever.py, graph/test_preferences.py, graph/test_interactive.py, graph/test_retriever.py, voice/test_livekit_agent.py]
