---
status: awaiting_human_verify
trigger: "Switch back to 6; remove Why it matches; speak/display a progress cue during generation; use matched detail in the recommendation"
created: 2026-08-17
updated: 2026-08-17T11:52:35-05:00
diagnose_only: false
---

# Voice progress and matched-detail alignment

## Symptoms

- expected_behavior: Results return to six; cards show only Matched detail (plus the Top recommendation badge); the final assistant recommendation speaks a real matched detail; a short progress cue is displayed and spoken during generation, then replaced by the single final answer with text and voice aligned.
- actual_behavior: Nine results increase latency; the top card duplicates Why it matches and Matched detail; the response reads a generic fit rationale; generation is silent and final text/audio do not feel simultaneous.
- error_messages: No runtime exception is reported.
- timeline: Observed after increasing the result limit from six to nine and adding canonical recommendation reasons.
- reproduction: Ask for a product with an age preference, observe both rationale boxes on the first card, then listen during the search and compare final text timing with speech.

## Current Focus

- hypothesis: Verified in automation; the only remaining blind spot is perceived cue/final timing and browser audio behavior in a real LiveKit room.
- test: Ask for a product with a preference in the live voice UI and observe the complete turn.
- expecting: One transient cue is displayed and spoken, then replaced by one final assistant answer whose audio matches its text; exactly six products render, the top card has one Matched detail block and no Why it matches block, and the final prose uses retrieved detail without inventing unsupported facets.
- next_action: Await human verification in the real LiveKit workflow; do not archive, stage, or commit before confirmation.
- reasoning_checkpoint:
    hypothesis: Nine constants cause result breadth; independent reason/detail renderers cause duplication; price-first reason selection causes generic final prose; absence of a non-durable cue speech call causes silent generation.
    confirming_evidence:
      - Revised cap tests observe nine products where six are required in graph, UI, interactive graph, and voice preview.
      - Revised card test directly observes the Why it matches block alongside Matched detail.
      - Revised answer test observes an in-budget generic price reason instead of available feature_evidence.
      - Voice regression cannot import the required cue constant, while source shows no progress session.say call and frontend tests show a visual-only pending cue.
    falsification_test: If changing only the identified constants/render branch/reason precedence/cue protocol does not make the isolated RED tests pass, or if final speech differs from assistant_result text, the hypothesis is incomplete.
    fix_rationale: Each source edit removes one confirmed cause at its ownership boundary; feature prose copies only retrieved feature_evidence, and add_to_chat_ctx=False keeps cue audio transient while the existing UI row is replaced by the final result.
    blind_spots: Automated tests cannot confirm perceived timing or browser autoplay in a real LiveKit room; final human verification must exercise the signed-in voice workflow.
- tdd_checkpoint: RED — cap, duplicate-card, matched-detail precedence, cue constant/event, and pending-copy tests fail against current source.

## Evidence

- timestamp: 2026-08-17T11:28:38-05:00
  observation: Screenshot shows a top-card “Why it matches” box immediately above a separate “Matched detail” box.
  implication: The same recommendation surface exposes two competing rationale channels.
- timestamp: 2026-08-17T11:32:28-05:00
  observation: The worktree already contains broad uncommitted changes across app, graph, voice, contracts, and tests, including new frontend reducer modules.
  implication: Investigation and any fix must operate on current file contents and avoid reverting, staging, or overwriting unrelated concurrent work.
- timestamp: 2026-08-17T11:33:40-05:00
  observation: graph/retriever.py defines TOP_K_PRODUCTS = 9, app/product_grid.py defines MAX_GRID_PRODUCTS = 9, and focused tests explicitly assert nine returned/rendered products.
  implication: The increased breadth is a coordinated graph/UI contract change, not an incidental extra row.
- timestamp: 2026-08-17T11:33:40-05:00
  observation: app/product_grid.py renders private.feature_evidence[0] as “Matched detail” and separately renders top_recommendation.reason as “Why it matches” for the same top card.
  implication: The duplicate rationale is caused by two independent render blocks in one card.
- timestamp: 2026-08-17T11:33:40-05:00
  observation: graph/recommendation.py returns a query/price rationale before considering feature_evidence, and graph/answer.py requires final prose to repeat that TopRecommendation.reason.
  implication: A generic query/price reason can displace the real retrieved matched detail in both generated and deterministic final prose.
- timestamp: 2026-08-17T11:33:40-05:00
  observation: voice/livekit_agent.py emits turn_started with an empty answer_text and no speech, then later emits assistant_result before session.say(final); the frontend already replaces one pending row with the final answer and rejects assistant audio transcriptions.
  implication: The missing spoken cue and text/audio sequencing live in the voice protocol; the UI already has a transient single-row lifecycle that can be reused.
- timestamp: 2026-08-17T11:33:40-05:00
  observation: Installed LiveKit AgentSession.say accepts add_to_chat_ctx=False.
  implication: The progress cue can be audible without entering durable assistant chat context, preserving one permanent final assistant answer.
- timestamp: 2026-08-17T11:35:08-05:00
  observation: The unchanged focused suite passes 61 Python tests and 11 frontend tests; named tests explicitly require nine result rows and only the completed final answer in session.spoken.
  implication: Existing regression expectations preserve the reported regression and must be updated before the implementation can be tested against the requested contract.
- timestamp: 2026-08-17T11:36:18-05:00
  observation: Revised tests fail with actual=9 vs expected=6 at graph, interactive graph, app grid, and Streamlit seams; the card still contains Why it matches; the in-budget recommendation chooses a generic price sentence over available feature_evidence; voice lacks PROGRESS_CUE; and frontend pending copy differs from the agreed cue.
  implication: Every requested behavior is reproducible through a focused failing assertion, and the root-cause branches are confirmed before source changes.
- timestamp: 2026-08-17T11:37:26-05:00
  observation: Initial fixes pass cap/card/answer/voice/frontend regressions, but an existing graph test loses the “does not confirm blue” caveat and Streamlit Match details still iterates uncapped result.products.
  implication: Grounded detail precedence must compose with honesty caveats, and all UI result surfaces—not only cards/table—must share the same six-item slice.
- timestamp: 2026-08-17T11:39:26-05:00
  observation: Full Python discovery passes 124 tests; the exact affected suite passes 62 tests; frontend passes 11 tests; Vite production build succeeds; stale-path scan finds both cap constants at six, no source Why it matches renderer, and one transient cue plus one final speech call.
  implication: The implementation is self-verified across graph, app, voice, frontend state, regression, and production-asset boundaries; only real-room human verification remains.
- timestamp: 2026-08-17T11:44:53-05:00
  observation: The voice protocol now queues both the transient cue and final grounded TTS before emitting their matching text events; a combined event/speech timeline regression passes, along with 124 full Python tests, 62 affected tests, 11 frontend tests, and the production build.
  implication: The known publish-before-speech race is removed in automation; perceived browser playback timing still requires one real-room check.
- timestamp: 2026-08-17T11:50:10-05:00
  observation: Final hardening waits up to 1.25 seconds for LiveKit's first-audio-frame `speaking` transition before publishing matching text, then falls back to text if audio startup is unavailable; duplicate final data packets are discarded before they can mutate transcript rows. Voice tests, 11 frontend tests, production build, and diff validation pass.
  implication: Text/audio release is aligned to actual playout rather than merely TTS scheduling, without allowing an audio failure to freeze the UI; the earlier duplicate-row risk is also closed.
- timestamp: 2026-08-17T11:51:18-05:00
  observation: The rebuilt stack starts cleanly, Streamlit health returns `ok`, LiveKit returns `OK`, and the voice worker registers as `product-discovery` against the restarted local server.
  implication: The final source and frontend bundle are active at http://localhost:8501; only human perception of real microphone playback remains unautomated because no controllable browser is attached.
- timestamp: 2026-08-17T11:52:35-05:00
  observation: Independent review found that a repeated identical request could be mistaken for a duplicate packet; resetting fast/result signatures in beginVoiceTurn closes the cross-turn collision while preserving within-turn deduplication. Frontend tests/build, 28 voice/app tests, and diff validation pass.
  implication: One final response is retained per turn without dropping a legitimate repeated shopper request.

## Eliminated


## Resolution

- root_cause: Coordinated nine-result caps, duplicate top-card rationale renderers, price-first recommendation rationale selection, and a visual-only/non-durable-missing voice turn-start protocol jointly caused the breadth, duplication, generic prose, and silent generation symptoms.
- fix: Restored six-result graph/UI caps; removed the top-card reason block; made retrieved feature_evidence drive canonical prose while retaining unconfirmed-facet caveats; queued one progress cue with add_to_chat_ctx=False, aligned matching text to LiveKit's first-audio-frame transition, waited for cue playout, then applied the same bounded playout alignment to the single identical final answer; reused the pending UI row, rejected duplicate final events before UI mutation, and rebuilt frontend assets.
- verification: 124 full Python tests, 62 exact affected Python tests, 11 frontend tests, and Vite production build all pass. Targeted source scan confirms six caps and no Why it matches renderer.
- files_changed:
    - graph/retriever.py
    - graph/recommendation.py
    - graph/test_retriever.py
    - graph/test_interactive.py
    - graph/test_answer.py
    - app/product_grid.py
    - app/main.py
    - app/test_product_grid.py
    - app/test_main.py
    - voice/livekit_agent.py
    - voice/test_livekit_agent.py
    - app/livekit_frontend/src/main.js
    - app/livekit_frontend/src/product_events.js
    - app/livekit_frontend/test/product_events.test.js
    - app/livekit_frontend/dist/index.html
    - app/livekit_frontend/dist/assets/index-CyLhv373.js
