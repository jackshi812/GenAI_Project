---
status: awaiting_human_verify
trigger: "The answer cuts off in the middle, and the wait time is slightly long; shorten it without compromising current functions"
created: 2026-08-17
updated: 2026-08-17T14:57:00-05:00
diagnose_only: false
---

# Complete answers with lower turn latency

## Symptoms

- expected_behavior: The assistant preserves the current grounded search, recommendation, matched-detail, six-card, voice, and synchronization behavior while answering in a complete natural sentence and responding a little faster.
- actual_behavior: A response ends mid-detail at “includes 7 body types, 9,” and the perceived wait before the final response is slightly too long.
- error_messages: No runtime exception is shown.
- timeline: Observed after matched catalog detail became the canonical spoken reason and first-audio-frame synchronization was added.
- reproduction: Ask for a product whose first catalog feature-evidence segment is long, then observe the generated/spoken reply after the progress cue.

## Current Focus

- hypothesis: Confirmed and fixed: raw feature-word slicing caused the incomplete sentence, and serialized cue startup delayed independent fast-reply work.
- test: Human-run the original Barbie-like voice turn in the real LiveKit/browser workflow.
- expecting: The cue remains transient and spoken, the final answer appears exactly once at its first audio frame, ends after a complete grounded clause, and begins sooner because fast work overlaps cue startup.
- next_action: Await human confirmation of the original workflow; archive only after confirmation.
- reasoning_checkpoint:
    hypothesis: Raw 12-word feature slicing causes the incomplete canonical sentence because the resulting full response is only 23 words and bypasses the TTS cap; awaiting cue first-frame synchronization before build_fast_reply independently adds the cue startup delay to the final-response critical path.
    confirming_evidence:
      - The actual AMZ-68E406F2-style detail deterministically becomes "Catalog evidence notes: The latest line of Barbie Fashionistas dolls includes 7 body types, 9." and the focused test fails on that exact output.
      - A delayed-session test records fast-reply work after progress-cue audio (timeline index 3 versus 1), proving serialization.
      - The real 14:04 tool log records rag.search at 234.4 ms and web.search at 1389.2 ms; preserving both searches while overlapping independent cue startup targets latency without removing evidence work.
    falsification_test: If clause-boundary compaction still produces the dangling item, or if fast work still begins after cue audio, or if cue/final text events precede their first audio frames, either proposed mechanism or fix is wrong.
    fix_rationale: Ending the excerpt at its last complete clause removes only a partial enumerated item while retaining verbatim matched catalog evidence; scheduling fast work before awaiting the cue first frame overlaps independent latency and leaves both synchronization awaits intact.
    blind_spots: Live provider/network latency cannot be reproduced in unit tests, and catalog excerpts without any clause punctuation still use the existing bounded fallback; end-to-end human verification remains required.
- tdd_checkpoint:

## Evidence

- timestamp: 2026-08-17T14:05:24-05:00
  observation: Screenshot shows “I’d recommend Barbie Fashionistas Doll with Long first. Catalog evidence notes: The latest line of Barbie Fashionistas dolls includes 7 body types, 9,” ending on a comma.
  implication: The displayed canonical answer is being mechanically truncated after generation rather than intentionally composed to fit its speech budget.
- timestamp: 2026-08-17T14:16:00-05:00
  checked: Debug knowledge base and repository search for speech-cap and voice-turn code.
  found: No knowledge-base entry overlaps this cutoff/latency symptom. cap_for_speech is centralized in voice/tts.py and is applied in both app/main.py and voice/livekit_agent.py; LiveKit awaits the progress handle and queues synchronized final speech in voice/livekit_agent.py.
  implication: This is not a known-pattern replay. Sentence completeness can be fixed centrally, while latency/order must be tested at the LiveKit orchestration boundary.
- timestamp: 2026-08-17T14:16:00-05:00
  checked: Worktree state before investigation.
  found: The worktree contains many pre-existing tracked and untracked changes, including voice/livekit_agent.py and voice/test_livekit_agent.py, while voice/tts.py and voice/test_tts.py are currently unmodified.
  implication: Any fix must preserve and build on the existing LiveKit changes and must not stage, revert, or overwrite unrelated work.
- timestamp: 2026-08-17T14:24:00-05:00
  checked: Complete voice/tts.py and the LiveKit turn path in voice/livekit_agent.py.
  found: cap_for_speech returns any input already at or below 30 words unchanged; only over-budget input retreats to a prior sentence. The screenshot text is roughly 23 words, so its comma ending must already exist upstream. Separately, on_user_turn_completed awaits progress-cue first-audio synchronization before it calls build_fast_reply, and that helper can wait up to VOICE_TEXT_SYNC_TIMEOUT_S (default 1.25 seconds).
  implication: Cutoff investigation moves upstream to graph answer composition. Latency has a specific async/timing candidate: independent cue startup and fast retrieval are currently serialized.
- timestamp: 2026-08-17T14:31:00-05:00
  checked: graph/recommendation.py with the reported long feature excerpt and voice cap.
  found: _compact uses the first 12 whitespace-delimited words. The excerpt "The latest line of Barbie Fashionistas dolls includes 7 body types, 9 skin tones..." becomes "The latest line of Barbie Fashionistas dolls includes 7 body types, 9"; _canonical_answer_text then produces a 23-word response, so cap_for_speech returns it unchanged.
  implication: Raw feature-evidence truncation is the confirmed cutoff mechanism; changing only voice/tts.py would not address it.
- timestamp: 2026-08-17T14:31:00-05:00
  checked: Existing focused unit tests under the system Python.
  found: voice.test_tts passes, but graph.test_answer and voice.test_livekit_agent cannot import because chromadb and livekit are absent from the system environment.
  implication: Verification must use the repository's configured virtual environment if present; this is an environment issue, not evidence against either hypothesis.
- timestamp: 2026-08-17T14:39:00-05:00
  checked: Focused pre-fix regressions under .venv.
  found: The answer regression failed with actual reason ending "7 body types, 9." instead of the expected complete clause. The delayed-session regression failed because fast work occurred after cue audio (timeline index 3 versus 1).
  implication: Both hypotheses are directly reproduced and confirmed; production fixes are justified.
- timestamp: 2026-08-17T14:46:00-05:00
  checked: The same two focused regressions after the production changes.
  found: Both pass. The long enumerated detail now ends at "7 body types." within the 30-word budget, and fast-reply work starts before delayed cue audio while cue/final event synchronization assertions pass.
  implication: Each minimal fix changes the predicted mechanism without weakening the tested response-order contract.
- timestamp: 2026-08-17T14:49:00-05:00
  checked: Complete graph.test_answer, voice.test_tts, and voice.test_livekit_agent suites.
  found: 25 tests pass with zero failures.
  implication: Adjacent answer grounding, speech boundary, product-count/provenance, canonical response, and audio/text ordering behavior remains intact.
- timestamp: 2026-08-17T14:52:00-05:00
  checked: Full Python unittest discovery and py_compile for the four changed source/test files.
  found: 125 tests pass with zero failures; all changed files compile. The suite includes six-result retrieval, catalog/live provenance, canonical top alignment, matched preference evidence, unsupported-facet caveats, MCP tool boundaries, and voice response ordering.
  implication: The minimal changes are compatible with the broader graph, catalog, MCP, launcher, and voice behavior.
- timestamp: 2026-08-17T14:57:00-05:00
  checked: Explicit app-facing suites and diff hygiene.
  found: 43 app tests pass with zero failures, and git diff --check reports no whitespace errors.
  implication: Streamlit/UI rendering boundaries remain compatible; self-verification is complete and only real audio/browser confirmation remains.

## Eliminated


## Resolution

- root_cause: graph.recommendation truncates catalog feature evidence at a raw 12-word boundary before the global speech cap, allowing an incomplete under-budget answer through. voice.livekit_agent separately awaits up to 1.25 seconds for progress-cue first audio before beginning independent fast-reply parsing/retrieval.
- fix: Compact overlong catalog feature evidence at the last complete clause within its word budget, and schedule build_fast_reply concurrently with progress-cue first-frame startup while retaining both text/audio synchronization waits.
- verification: Two focused regressions changed from red to green; 25 adjacent graph/voice tests, 125 discovered repository tests, and 43 explicit app tests pass; changed files compile and diff hygiene passes. Real LiveKit/browser audio latency requires human confirmation.
- files_changed: [graph/recommendation.py, graph/test_answer.py, voice/livekit_agent.py, voice/test_livekit_agent.py]
