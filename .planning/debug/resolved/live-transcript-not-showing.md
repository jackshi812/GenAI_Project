---
status: resolved
trigger: "When I record and speak, the live transcript is not showing"
created: 2026-08-16
updated: 2026-08-16
diagnose_only: false
---

# Live microphone transcript not showing

## Symptoms

- expected_behavior: While the microphone is active and the user speaks, interim recognized words appear in the live transcript area.
- actual_behavior: The live transcript does not appear while recording and speaking.
- error_messages: No error was reported in the UI.
- timeline: Observed in the current build; whether an earlier build worked is unknown.
- reproduction: Start the microphone, speak, and watch the live transcript area.

## Current Focus

- hypothesis: Confirmed — the browser accepted only streams whose reported sender identity exactly matched the shopper, so agent-forwarded shopper transcriptions could be discarded before rendering.
- test: Browser helper regressions, production frontend build, full Python suite, and the real local LiveKit voice smoke test.
- expecting: Forwarded shopper microphone text is accepted, assistant text is rejected, partial chunks update one visible bubble, and the final marker is read after stream closure.
- next_action: Resolved and verified; refresh the browser to load the content-hashed bundle.
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- timestamp: 2026-08-16T20:45:00Z
  observation: The frontend returned early unless participantInfo.identity exactly equaled room.localParticipant.identity; it did not inspect lk.transcribed_track_id.
- timestamp: 2026-08-16T20:46:00Z
  observation: The installed LiveKit Agents output includes lk.transcribed_track_id and can publish a shopper transcript through the agent participant. LiveKit's documented frontend contract identifies transcription streams with that attribute.
- timestamp: 2026-08-16T20:47:00Z
  observation: The frontend computed lk.transcription_final from the opening header, although LiveKit adds the final=true value to the stream trailer after reading completes.
- timestamp: 2026-08-16T20:54:00Z
  observation: The real local voice smoke test observed an interim transcript while speech was still playing, a fast reply at 1256 ms, and first answer audio at 3185 ms, confirming the upstream STT and LiveKit path works.
- timestamp: 2026-08-16T20:54:54Z
  observation: Four browser-side transcript regressions, 75 repository tests, and 15 focused app/voice tests pass; the production component builds and Streamlit health returns ok.

## Eliminated

- hypothesis: OpenAI STT or the LiveKit agent never emits interim text.
  reason: The end-to-end local voice smoke test received an interim transcription before speech finished.
- hypothesis: The Streamlit Python graph must rerun for every partial word.
  reason: The transcript is intentionally rendered inside the persistent browser component; rerunning Streamlit for each partial would interrupt the live room.

## Resolution

- root_cause: The browser used sender identity as its only speaker test. Agent-forwarded text streams can report the agent as sender even though lk.transcribed_track_id points to the shopper microphone, causing valid user text to be silently ignored. The same handler also read the final flag before LiveKit applied trailer attributes.
- fix: Accept transcripts when either the sender is the shopper or the transcribed track is the local microphone; reject assistant-track text; create the listening bubble immediately; safely merge delta and cumulative chunks; read the final flag after stream completion; and surface stream errors instead of failing silently.
- verification: Browser helper tests pass 4/4, the production Vite bundle builds, all 75 repository tests and 15 focused app/voice tests pass, the real local voice smoke test receives interim text, and Streamlit reports healthy.
- files_changed: app/livekit_frontend/src/main.js, app/livekit_frontend/src/transcript.js, app/livekit_frontend/test/transcript.test.js, app/livekit_frontend/package.json, and rebuilt app/livekit_frontend/dist assets.
