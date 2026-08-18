---
status: resolved
trigger: "Can you access my latest chat with the agent? It is still stupid. Please please make it genuinely smart. Also sometimes the text appear before the message"
created: 2026-08-17
updated: 2026-08-17
diagnose_only: false
---

# Smart conversation and deterministic message order

## Symptoms

- expected_behavior: The assistant should interpret the whole conversation, adapt naturally to preference changes and vague replies, and render each user turn before any thinking text, assistant response, or product update caused by that turn.
- actual_behavior: Recent replies still feel fixed or context-blind, and some text appears before the message that triggered it.
- error_messages: No explicit exception was reported.
- timeline: This is a recurrence after several earlier response-quality and frontend-ordering fixes.
- reproduction: Hold a normal multi-turn shopping conversation, change or clarify preferences, and observe both reply relevance and the order in which transcript/message/status events appear.

## Current Focus

- hypothesis: Confirmed. The voice fast path became the final answer for clarification/refinement/selection turns, internal web-routing text was appended to shopper input, acknowledgements were classified as new product names, and transcript/product events had no causal commit boundary.
- test: Regression coverage now exercises short acknowledgements, source-word stripping, metadata-only live routing, full-graph voice clarification, one canonical spoken answer, canonical transcript commit, late-transcript rejection, and typed UI commit acknowledgement.
- expecting: One canonical assistant response per turn, generated from accumulated preferences and grounded candidates, with UI events sequenced by turn before products and speech.
- next_action: Resolved; monitor real conversations for new intent classes rather than adding response templates.
- reasoning_checkpoint: Preserve grounding: intelligence must come from better state interpretation and synthesis, never invented product facts.
- tdd_checkpoint: GREEN — 113 Python tests and 11 frontend tests pass.

## Evidence

- timestamp: 2026-08-17T09:45:00-05:00
  observation: Browser discovery returned no connected tabs, so the visible bubbles cannot be read directly from the user's browser session.
  implication: Reconstruct the latest exchange from application events/logs if retained and trace the implementation rather than claiming visual access.

- timestamp: 2026-08-17T10:07:00-05:00
  observation: The retained MCP audit log contained literal queries including `Yeah web` and combined unrelated earlier phrases with later product requests.
  implication: The defect was upstream intent/query construction, not merely response tone.

- timestamp: 2026-08-17T10:20:00-05:00
  observation: Focused RED tests failed on acknowledgement context, social/source query cleanup, metadata live routing, and voice graph bypass; all passed after the implementation changes.
  implication: The fixes directly cover the reproduced failure mechanisms.

- timestamp: 2026-08-17T10:24:00-05:00
  observation: A real configured-model smoke test retained `groceries` for the reply `Yeah` and generated `Great—did you mean pantry staples or fresh ingredients for your groceries under $20?`
  implication: The production model path now uses the prior assistant question instead of treating the reply as a product name.

- timestamp: 2026-08-17T10:25:00-05:00
  observation: Full Python discovery passed 113 tests, frontend Node tests passed 11 tests, frontend production build succeeded, `git diff --check` passed, and the restarted Streamlit health endpoint returned HTTP 200.
  implication: Backend behavior, event ordering, compiled frontend assets, and local service startup are verified.

## Eliminated


## Resolution

- root_cause: The app had competing orchestration paths. Several voice turn kinds returned deterministic fast-copy without invoking the conversation-aware graph; live routing was encoded by mutating the shopper transcript; short acknowledgements were considered new noun phrases; the last assistant question was not retained separately from product evidence; and independent transcript/component/Streamlit events could render out of order.
- fix: Route every completed voice turn through the full graph; pass `force_live` as dialogue metadata; classify yes/no acknowledgements as contextual; provide the prior assistant answer to preference/dialogue calls; replace the canned no-match sentence with bounded natural dialogue; emit an immediate turn-start event; commit the canonical transcript before thinking/answer events; ignore late transcript chunks; and wait for a typed-chat commit acknowledgement before exposing result cards.
- verification: 113 Python tests, 11 frontend tests, Python compilation, Vite production build, real-model context smoke tests, clean diff check, process/port inspection, and HTTP 200 health check.
- files_changed: `graph/preferences.py`, `graph/fast_reply.py`, `graph/interactive.py`, `graph/dialogue.py`, `prompts/preferences.md`, `prompts/dialogue.md`, `voice/livekit_agent.py`, `app/main.py`, frontend event/transcript modules and their regression tests.
