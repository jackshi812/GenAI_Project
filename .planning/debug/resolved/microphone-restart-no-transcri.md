---
status: resolved
trigger: "On the page start mic only works for the first time. After stop recording and start mic again, words are not transcribed."
created: 2026-08-20
updated: 2026-08-20
diagnose_only: false
---

# Microphone restart does not transcribe

## Symptoms

- expected_behavior: Starting the microphone after stopping it resumes live transcription in the same chat.
- actual_behavior: The first microphone session transcribes, but speech after stop and a second start is not transcribed.
- error_messages: No visible error was reported.
- timeline: Present in the current page lifecycle; the first microphone session works.
- reproduction: Start mic, speak, stop mic, start mic again, and speak.

## Current Focus

- hypothesis: Confirmed — Stop mic disconnects the shopper from the LiveKit room, which closes the linked agent session instead of pausing only the microphone track.
- test: Browser-side lifecycle regression covers pause then resume on the same room.
- expecting: Confirmed — Stop mutes the local microphone without disconnecting; the next start unmutes the same track and keeps transcription context alive.
- next_action: Resolved and verified; refresh the page to load the rebuilt component bundle.
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- timestamp: 2026-08-20T00:00:00Z
  observation: app/livekit_frontend/src/main.js stopConversation calls room.disconnect(), clears room, and clears connectedRoom.
- timestamp: 2026-08-20T00:00:01Z
  observation: Installed LiveKit Agents RoomOptions defaults close_on_disconnect to true and closes AgentSession for a client-initiated linked-participant disconnect.
- timestamp: 2026-08-20T00:00:02Z
  observation: Installed livekit-client setMicrophoneEnabled(false) mutes an existing microphone publication, while true unmutes it, preserving the room participant and agent session.
- timestamp: 2026-08-20T14:38:00Z
  observation: The new browser regression exercises stop then start as false/true microphone states on the identical room and asserts that disconnect is never called.
- timestamp: 2026-08-20T14:39:00Z
  observation: The final browser suite passes 20/20, the production Vite bundle builds, all 163 Python tests pass, focused LiveKit component and agent tests pass 17/17, and git diff validation is clean.

## Eliminated

- hypothesis: The browser cannot reactivate an existing microphone track.
  reason: livekit-client explicitly implements setMicrophoneEnabled(false/true) as mute/unmute for an already-published microphone track.

## Resolution

- root_cause: Stop mic called room.disconnect(), and LiveKit Agents closes its linked AgentSession by default for that client-initiated participant disconnect. A second browser join therefore did not resume the original STT session or its conversational context.
- fix: Stop mic now mutes the published microphone track and retains the connected room; Start mic unmutes that same room. Unexpected mute failures still disconnect as a privacy-safe fallback, and UI listening state now follows microphone activity rather than room existence.
- verification: Browser lifecycle regression passes, all 20 frontend tests pass, the production component bundle builds and contains the pause/resume path, all 163 Python tests pass, 17 focused LiveKit component/agent tests pass, and git diff validation reports no whitespace errors.
- files_changed: app/livekit_frontend/src/main.js, app/livekit_frontend/src/microphone_session.js, app/livekit_frontend/test/microphone_session.test.js, app/livekit_frontend/dist/index.html, and rebuilt app/livekit_frontend/dist/assets/index-et07JLnW.js.
