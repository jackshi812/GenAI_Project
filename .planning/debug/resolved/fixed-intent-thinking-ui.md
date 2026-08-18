---
status: resolved
trigger: "Looks like the agent is still dumb and answers are based on a fixed structure. Can you please check deep into this issue and genuinely make it more intelligent? Also instead when the agent is thinking, please indicate it's thinking instead of having the message box suddenly pop up."
created: 2026-08-16
updated: 2026-08-16
diagnose_only: false
---

# Fixed intent handling and missing thinking state

## Symptoms

- expected_behavior: After an under-$10 clarification, “I need something for home” should advance to a home-specific narrowing question, retain the $10 budget, and never repeat the generic menu. A visible pending assistant row should remain until the canonical answer replaces it.
- actual_behavior: The assistant repeats the exact generic clarification template and the final message appears abruptly without a pending assistant state.
- error_messages: No exception is shown.
- timeline: Reproduced in the current conversational-preference build.
- reproduction: Ask for anything under $10, then answer the clarification with “I need something for home.”

## Current Focus

- hypothesis: Confirmed and expanded: the use case was stored as a feature on placeholder `product`; normal model calls timed out into canned text; voice then applied the updated profile twice; the frontend had no immediate pending row and accepted stale completed typed turns.
- test: Parser, two-turn graph, voice context, response policy, stale event, transcript, and full local suite regressions.
- expecting: Each turn is interpreted once, vague home intent receives a contextual question, explicit delegation still chooses, and one thinking row is atomically replaced by one final response.
- next_action: None.
- reasoning_checkpoint: The right behavior for “home” is another focused clarification, not an arbitrary broad home search; “help me decide” remains the explicit autonomous-selection signal.
- tdd_checkpoint: Regressions failed before the fixes and pass after them.

## Evidence

- `resolve_preferences` originally produced `product_query="product"`, `features=["home"]` for the second turn.
- The configured model took roughly 2.9–4.0 seconds in isolated calls, while preference, decision, and answer stages allowed only 2.0–2.5 seconds, forcing deterministic fallback wording.
- The voice path replaced `dialogue_context.shopping_context` with the fast parser's current-turn profile before the full graph processed the same utterance again.
- The old frontend showed fast output or nothing before the final event and did not correlate a completed external turn with the currently pending typed request.

## Eliminated

- Catalog retrieval itself was not the cause of the repeated clarification.
- The model configuration and API key were present; the short timeout made the model effectively unavailable.
- Duplicate display/speech generation was already eliminated; the remaining repetition came from intent state and stale event handling.

## Resolution

- root_cause: Misclassified category-level intent, timeouts shorter than real model latency, current-turn preference state passed back as prior state, canned clarification fallback, and missing pending/stale-event UI guards.
- fix: Added catalog use-case interpretation; made broad `home` a contextual clarification; added a bounded LLM dialogue stage with contextual claim-free fallback; raised selective LLM timeouts to six seconds; preserved pre-turn context through the voice graph; added immediate pulsing “Thinking…” rows and request correlation.
- verification: 86 Python tests pass, 7 frontend tests pass, the production bundle builds, Streamlit health returns `ok`, and LiveKit plus the voice worker are connected locally.
- files_changed: `graph/preferences.py`, `graph/relevance.py`, `graph/dialogue.py`, `graph/response_style.py`, `graph/fast_reply.py`, `graph/interactive.py`, `graph/nodes.py`, `graph/answer.py`, `voice/livekit_agent.py`, `app/main.py`, and `app/livekit_frontend/` source/tests/dist.
