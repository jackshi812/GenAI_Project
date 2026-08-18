---
status: awaiting_human_verify
trigger: "One chat can only handle one request: after finding toy animals, saying 'I want some vegetables' confuses the agent instead of moving to the next item."
created: 2026-08-17
updated: 2026-08-17T00:00:00-05:00
diagnose_only: false
---

# Switch cleanly to a new product within one chat

## Symptoms

- expected_behavior: A clearly different product request such as "I want some vegetables" automatically starts a fresh product search, while genuine facet/preference follow-ups continue refining the current item. Explicit transition language such as "now I need" or "next, find" must also start a new item.
- actual_behavior: After a successful toy-animal request, the agent is confused by "I want some vegetables" and appears to retain or combine the prior product context.
- error_messages: No runtime exception is reported.
- timeline: Reproduced in the latest chat after multi-turn preference memory was added.
- reproduction: In one chat, request toy animals and receive results; then say "I want some vegetables."

## Non-negotiable regression contract

- Preserve short positive and negative preference follow-ups such as "make it blue," "not black," size, material, comfort, and budget changes.
- Preserve confirmations, rejections, delegated choices, and references such as "the second one."
- Preserve six grounded results, exclusions, canonical recommendation alignment, citations, natural answers, progress speech, and text/audio synchronization.
- Do not require users to say a magic reset phrase when the new product category is already clear.

## Current Focus

- hypothesis: Confirmed fix is self-verified; production voice/UI behavior now needs human confirmation in the real workflow.
- test: In one live chat, search toy animals, then request vegetables with bare and explicit transition wording; verify past-tense cart acknowledgement is conversational and imperative cart wording does not claim an action.
- expecting: Each vegetable request starts a clean grocery search with no toy facets or old budget, real facet/reference turns still refine the active item, and `Okay added cart` makes no product search.
- next_action: Project owner performs the live voice/UI verification and reports `confirmed fixed` or the remaining failing phrase/behavior.
- reasoning_checkpoint:
    hypothesis: "Explicit transition phrases fail because query cleanup and novelty classification do not share a transition grammar: `next` survives semantic cleanup and `also` triggers the generic change-cue early return before product/category inference. Completed-cart statements fail independently because no social-intent pattern catches them, so ordinary product parsing treats `added cart` as a noun phrase."
    confirming_evidence:
      - "Direct probes produce `next vegetables`, retain `toy animals` for `I also want vegetables`, and produce product query `Okay added cart`."
      - "Focused RED tests fail at preference, fast-reply, and full interactive graph boundaries with stale context, malformed query, or unwanted tool calls; the pronoun-facet control test passes."
      - "Live MCP evidence independently shows the exact `I want some vegetables` path already reaches grocery RAG, ruling out retrieval or voice persistence as the cause of that exact current turn."
    falsification_test: "The hypothesis is false if a shared transition cleanup plus bounded cart-social classification does not make the same focused tests pass, or if positive/negative/pronoun facet controls begin resetting context."
    fix_rationale: "Recognizing and stripping only explicit new-item prefixes makes the routing decision and retrieval query agree, while checking the remainder prevents facet-only turns from resetting. Classifying only completed-cart wording as conversation stops bogus retrieval without claiming or implementing cart mutation."
    blind_spots: "The live LLM graph mode and production speech transcription may yield additional paraphrases not covered here; the fix is intentionally limited to deterministic interactive/fast paths and explicit cue families observed or required."
- tdd_checkpoint:

## Evidence

- timestamp: 2026-08-17T00:00:00-05:00
  checked: Debug knowledge base against keywords from the current symptom (`toy animals`, `vegetables`, `prior context`, `confused`).
  found: The only knowledge-base entry concerns recommendation identity/budget parsing and has no two-keyword overlap with this context-switch symptom.
  implication: There is no archived known-pattern shortcut; investigate the live parser and state boundaries directly.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Repository status and symbol search for ShoppingContext, follow-up detection, preference resolution, and context persistence.
  found: The worktree already contains extensive modified and untracked implementation work across graph, app, voice, catalog, frontend, and planning files; the shared logic is concentrated in `graph/preferences.py`, consumed by both `app/main.py` and `voice/livekit_agent.py`.
  implication: Preserve all existing changes and first isolate the bug in the shared deterministic parser before touching integration layers.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Exact deterministic parser probe with prior `ShoppingContext(product_query='toy animals')` and turn `I want some vegetables`.
  found: `semantic_query` returns `vegetables`; `is_new_product_request` is true; contextual follow-up classification is false; `resolve_preferences` returns a fresh `vegetables` context with no inherited facets and `is_followup=false`.
  implication: The shared preference parser correctly performs the requested category reset; the original parser hypothesis is disproved.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Sanitized latest MCP execution evidence supplied by the orchestrator.
  found: The live run queried private RAG for `vegetables` in Grocery & Gourmet Food and got 11 results, but the web query became `vegetables groceries fresh preferably` and returned zero; a later `just need vegetables` turn produced 12 live vegetable results. The subsequent `Okay added cart` acknowledgement was treated as a new RAG/web search.
  implication: Automatic product switching is operational at parser and retrieval boundaries; the perceived confusion is downstream transition UX/no-live handling, with an adjacent false-positive shopping-search classification for cart acknowledgement.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Interactive planner and retriever web-query construction.
  found: With reliable private results, the interactive retriever intentionally forms its single live-enrichment query from the top catalog title via `eight_word_key`; therefore `vegetables groceries fresh preferably` came from a grounded catalog title, not inherited toy context or invented shopper facets. Zero matching live hits do not discard the six private candidates.
  implication: The zero-hit live lookup is not evidence of context leakage. Focus the fix on uncovered transition/acknowledgement classification rather than changing grounded retrieval semantics.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: First transition-matrix command driver.
  found: The driver failed at Python parse time because a compound `async def` followed a semicolon; no project code executed.
  implication: Correct the probe syntax and rerun; this result neither supports nor refutes any product hypothesis.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Corrected deterministic classification matrix with prior toy-animal facets.
  found: `I want some vegetables` and `now I need vegetables` cleanly reset to `vegetables`; `next, find vegetables` resets but produces product query `next vegetables`; `I also need vegetables` and `also vegetables` remain follow-ups on `toy animals` with its blue/black facets; `Okay added cart` becomes a fresh product query. Positive/negative facets, `the second one`, and confirmation language retain context as required.
  implication: The root defects are deterministic grammar gaps, not LLM variance, retrieval state, or audio timing. Focused classification changes can preserve the proven regression contract.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Six focused pre-fix regressions across preference parsing, fast reply, and the full interactive graph.
  found: The suite failed exactly on malformed `next vegetables`, stale toy context/no retrieval for `I also want vegetables`, and unwanted retrieval or clarification for completed-cart language; the `I also want it green` facet control passed.
  implication: The root cause is reproduced automatically at every affected boundary, and the passing control demonstrates a narrow fix can distinguish new items from genuine pronoun facets.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: First focused post-fix run.
  found: Fast and full graph switching, cart acknowledgement, `next`, `now`, and `also` cases passed; only `Moving on, let's look for vegetables` still resolved to `product` rather than `vegetables`.
  implication: The causal hypothesis is supported, but the shared transition grammar has one remaining overmatch/cleanup edge case to isolate before broader verification.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Transition helper and semantic query output for `Moving on, let's look for vegetables`.
  found: Both correctly returned `vegetables`; `_USE_CASE_FEATURE` separately interpreted the original `for vegetables` phrase as a feature and stripped the product during rule resolution.
  implication: Facet extraction for explicit transition turns must operate on the already stripped product phrase, while merge/replace semantics can continue using the original turn.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Focused post-fix suite after applying transition-prefix cleanup, transition-remainder facet parsing, cart-completion classification, and fast-path social context preservation.
  found: All 6 focused tests passed, covering six explicit cue phrasings, pronoun facet retention, fast/full category reset with old budget/facets present, and zero-tool cart acknowledgement with context retention.
  implication: The minimal changes causally resolve every reproduced boundary failure; proceed to regression verification.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Complete directly affected preference, fast-reply, and interactive graph test modules.
  found: All 76 tests passed. The only stderr was Arrow sandbox warnings for unavailable macOS CPU cache sysctls; the test process exited successfully.
  implication: Existing follow-ups, retrieval routing, grounding, conversation turns, and interactive orchestration remain intact within the directly changed modules.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Adjacent retrieval, answer, response-style, dialogue, LiveKit voice, Streamlit app, and product-grid suites.
  found: All 71 tests passed. Bare-mode Streamlit warnings were expected and non-failing.
  implication: The current fix preserves adjacent grounding, recommendation, citation, voice, and UI contracts; one requested bare-`also` transition case remains to add before final verification.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Pre-fix bare-`also` regressions and facet/domain controls.
  found: `Also vegetables` failed at parser, fast, and full graph boundaries by retaining toy context; `also blue`, `also padded`, and iPhone `also camera` remained contextual, though camera wording still contained the cue.
  implication: Bare `also` requires a product/category-gated transition branch rather than removal of the general change-cue safeguard.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Focused suite after product/category-gated bare-`also` support.
  found: All 6 focused tests passed, including bare vegetables across parser/fast/full graph and facet/domain controls; transition cleanup also normalized the phone feature to `camera`.
  implication: The stricter bare-cue gate resolves the requested switch without converting generic facets or active-product domain features into new searches.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Combined final regression suite across preference, fast/full graph, retriever, answer, response style, dialogue, LiveKit voice, Streamlit app, and product grid.
  found: All 147 tests passed in 24.147 seconds. Only expected Arrow sandbox sysctl and bare-mode Streamlit warnings appeared.
  implication: Product transition, facet/referral, grounding, exclusions, six-card, citation, recommendation, voice, and UI contracts remain green after the complete fix.
- timestamp: 2026-08-17T00:00:00-05:00
  checked: Final compileall, focused six-test rerun, scoped whitespace/error diff check, and implementation review.
  found: Compilation passed, all 6 focused tests passed again, and `git diff --check` reported no errors. The scoped implementation adds classification/normalization and a past-tense acknowledgement only; it does not add cart storage or mutation behavior.
  implication: Automated verification is complete and the dirty worktree is preserved without staging or commits; only real voice/UI confirmation remains.

## Eliminated

- hypothesis: `graph/preferences.py` retains toy-animal context for `I want some vegetables`.
  evidence: The exact deterministic probe returns a fresh, facet-free `vegetables` ShoppingContext, and the latest live trace independently shows RAG queried `vegetables` in the grocery category.
  timestamp: 2026-08-17T00:00:00-05:00

## Resolution

- root_cause: Explicit new-item cue parsing was inconsistent across semantic cleanup and novelty classification: leading `next`/`moving on` language remained in product queries, while blanket `also` change-cue handling ran before product/category inference and retained the prior ShoppingContext. Independently, completed-cart acknowledgements had no conversation-intent rule, so `added cart` was parsed and retrieved as a product phrase.
- fix: Added a shared next-item prefix grammar used by both semantic-query cleanup and novelty classification; explicit cues evaluate the remaining non-facet product phrase, while bare `also` resets only for a recognized product/category and not active-product domain features. Rule resolution now extracts facets from the stripped transition remainder. Added a bounded past-tense completed-cart conversation pattern and preserved the prior ShoppingContext on fast-path social replies; imperative cart requests remain outside this acknowledgement rule. Added focused preference, fast-path, and full-graph regressions.
- verification: RED tests reproduced malformed/stale transitions and bogus cart retrieval; focused GREEN suite passed 6/6. Complete affected and adjacent regression suite passed 147/147 in 24.147 seconds. Changed modules compile, scoped diff check passes, explicit/bare transition controls preserve positive/negative/domain follow-ups, and imperative cart requests are not misreported as completed actions. Human live workflow verification remains pending.
- files_changed: [graph/preferences.py, graph/fast_reply.py, graph/test_preferences.py, graph/test_fast_reply.py, graph/test_interactive.py]
