---
status: resolved
trigger: "Also seems that the agent is generating multiple responses but the voice only contains one"
created: 2026-08-16
updated: 2026-08-16
diagnose_only: false
---

# Voice response does not match visible responses

## Symptoms

- expected_behavior: One coherent assistant response per shopper turn, with spoken audio matching the complete response shown in chat.
- actual_behavior: Multiple assistant responses appear to be generated, but voice playback contains only one of them.
- error_messages: No error was reported.
- timeline: Observed in the current fast-reply plus full-graph voice build.
- reproduction: Submit a shopping request through the live microphone path and compare assistant chat updates with the spoken audio.

## Current Focus

- hypothesis: Confirmed and fixed.
- test: Trace and regression-test one turn from fast preview through completed graph result, frontend presentation, and LiveKit speech.
- expecting: Exactly one canonical response is committed to chat and speech.
- next_action: None.
- reasoning_checkpoint: Fast evidence remains useful as a right-side loading preview, but is not a conversational response. The completed graph answer is capped once, then the identical text is displayed and spoken.
- tdd_checkpoint: The new canonical-response test failed against the old fast-first speech behavior, then passed after the fix.

## Evidence

- The old `on_user_turn_completed` called `session.say(fast.text)` before the full graph ran.
- The background path later emitted a different `assistant_result.answer_text` and only spoke again for certain live-search followups.
- Live requests could emit a preliminary web `assistant_result` and then a full graph `assistant_result`, creating up to three textual answer states for one turn.
- The frontend marked the turn ready immediately on `fast_reply`, allowing microphone activity to create another chat row before the completed result arrived.
- The red regression reproduced the mismatch exactly: speech was `I found a quick catalog option.` while the emitted completed answer was a different product explanation.

## Eliminated

- TTS truncation was not the primary cause; the agent selected the wrong response stage before synthesis.
- Remote audio attachment was working; the missing content was never submitted to `session.say`.

## Resolution

- root_cause: The fast preview, preliminary web result, and completed graph result were all treated as user-facing answers, while speech had a separate conditional path. The frontend also finalized the voice turn on the preview event.
- fix: Treat `fast_reply` as preview data only, keep the voice turn pending, remove preliminary response publication from the active path, cap the completed graph answer to 30 words, and use that exact same text for the single `assistant_result` and `session.say` call. If the graph fails, the grounded fast result becomes the single canonical fallback.
- verification: The focused Python voice/TTS suite passed 7 tests; the frontend passed 6 tests including preview-versus-final policy checks; the full Python suite passed 79 tests; the frontend production bundle built successfully; compilation and `git diff --check` passed; the running app health endpoint returned `ok`.
- files_changed: `voice/livekit_agent.py`, `voice/test_livekit_agent.py`, `app/livekit_frontend/src/main.js`, `app/livekit_frontend/src/product_events.js`, `app/livekit_frontend/test/product_events.test.js`, and rebuilt frontend assets.
