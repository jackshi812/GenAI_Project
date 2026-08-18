---
status: awaiting_human_verify
trigger: "The recommendation ends with 'it does not confirm my kid,' and there is no audio when the user types a message."
created: 2026-08-17
updated: 2026-08-17T15:18:00-05:00
diagnose_only: false
---

# Remove invalid caveats and speak typed turns

## Symptoms

- expected_behavior: Recommendations should use natural grounded match details without treating phrases such as "my kid" as a missing product attribute. Typed requests should receive the same single synchronized spoken final answer as microphone requests.
- actual_behavior: A LEGO recommendation ends with "it does not confirm my kid." Requests submitted by typing display a final response but produce no assistant audio.
- error_messages: No runtime exception is shown.
- timeline: Observed in the current app after matched-detail and voice/text synchronization changes.
- reproduction: Ask for "LEGO for my kid" and inspect the final caveat. Then type a product request using the text input and observe that the assistant response is silent.

## Current Focus

- hypothesis: All confirmed root causes and follow-up audit boundaries are fixed: recipient-only phrasing is sanitized, negative evidence caveats are rejected, feature detail is clause-safe, canonical answers stay within 30 words, and typed lifecycle epochs prevent stale/overlapping commits.
- test: Human verification in the real browser/audio environment for exact LEGO typed inputs, restart/voice transition, and one microphone request.
- expecting: The exact feature is spoken as `open-ended play`; typed answers play once and stay within 30 words; restart or voice start stops stale typed audio without affecting LiveKit final audio; no negative caveat appears.
- next_action: Ask the user to verify typed speaker output, restart/typed-to-voice behavior, and the LiveKit microphone path end to end.
- reasoning_checkpoint:
    hypothesis: "Recipient regex coverage, negative-caveat validation, and typed lifecycle identity each omit the exact boundary shown by the RED tests: alternate determiners/suffixes survive, paraphrased evidence failure contains no literal requested term, and request ID alone cannot invalidate an already-awaiting synchronization callback."
    confirming_evidence:
      - "The `.venv` recipient regression returns `features=['my kid please']` and `features=['a kid']` for the two audited inputs."
      - "The `.venv` natural-answer regression accepts `The evidence does not confirm your preferred sizing.` even with unsupported size preferences."
      - "Source tracing shows restart stops typed audio but an awaiting synchronization callback has no epoch guard; `beginVoiceTurn` does not stop typed playback at all."
    falsification_test: "If determiner/suffix normalization, a generic negative-evidence pattern, and an epoch-plus-request predicate do not independently make their focused regressions green, the causal model is incomplete."
    fix_rationale: "Normalize recipient-only phrases at the parser boundary, reject negative evidence-failure wording before accepting natural drafts, and centralize monotonic typed-turn lifecycle state so restart, voice start, and new typed submission all invalidate and stop only the typed WebAudio source before any stale commit or acknowledgement."
    blind_spots: "Node tests can verify epoch and separate-controller behavior, but physical speaker/microphone playback still requires the existing real-browser human checkpoint."
- tdd_checkpoint:
    test_file: graph/test_answer.py
    test_name: test_short_feature_detail_keeps_complete_open_ended_play_clause
    status: green
    failure_output: "RED reproduced `allow for open-ended.`; GREEN preserves `allow for open-ended play.`"

## Evidence

- timestamp: 2026-08-17
  observation: Screenshot shows a grounded LEGO recommendation followed by "it does not confirm my kid." User reports that typed turns have no audio.
  implication: The displayed answer is adding an invalid unsupported-facet caveat, and typed messages are not sharing the microphone turn's spoken final-response contract.
- timestamp: 2026-08-17
  checked: Repository state and project skill directories.
  found: The worktree already contains extensive modified and untracked implementation files; no project-defined `.codex/skills` or `.agents/skills` were found.
  implication: Treat all existing source changes as user/other-agent work and patch only confirmed lines without reverting, staging, or committing.
- timestamp: 2026-08-17
  checked: Exact caveat text and typed/microphone dispatch symbol search.
  found: `graph/recommendation.py` constructs `"; it does not confirm " + missing_preferences`; the typed frontend sends a `typed_message` component event while microphone results arrive over LiveKit `product.discovery` data and remote audio tracks.
  implication: The caveat has a deterministic renderer whose input can be tested independently, while typed audio requires tracing the distinct component-event backend path into LiveKit speech.
- timestamp: 2026-08-17
  checked: Complete preference extraction and recommendation rendering functions plus adjacent regressions.
  found: `_USE_CASE_FEATURE` captures every phrase after the word `for`; `_generic_features` rejects only `me/us/you` as recipients, so `for my kid` remains a positive free-form feature and is later treated as evidence-required by `recommendation_reason`.
  implication: The implementation directly supports the extractor-to-renderer mechanism, but a runtime probe is needed to confirm exact values.
- timestamp: 2026-08-17
  checked: Deterministic preference extraction probe for `LEGO for my kid`.
  found: The project runtime returned `product_query="LEGO"`, `features=["my kid"]`, and `resolved_query="LEGO my kid"`.
  implication: The extractor half of the hypothesis is confirmed exactly; the recipient phrase is being misclassified as an evidence-verifiable product requirement.
- timestamp: 2026-08-17
  checked: Isolated recommendation rendering with that context and grounded LEGO feature evidence.
  found: `recommendation_reason` returned `Catalog evidence notes: Includes astronaut figures and a space rover; it does not confirm my kid.` exactly.
  implication: The complete causal chain for the invalid caveat is confirmed; no LLM or external service is involved.
- timestamp: 2026-08-17
  checked: New focused preference regression before the parser fix.
  found: The test failed exactly because actual `features` was `["my kid"]` instead of `[]`.
  implication: The regression directly reproduces the root-cause input and will distinguish a causal parser fix from unrelated renderer suppression.
- timestamp: 2026-08-17
  checked: Focused regression after filtering recipient-only phrases from feature extraction.
  found: The feature assertion no longer failed, but `product_query` became `LEGO my kid` instead of `LEGO` because `_strip_facets` only removes phrases present in facet updates.
  implication: The first change removed the invalid caveat input but exposed a second deterministic query-cleaning seam; the recipient phrase must be ignored in both outputs.
- timestamp: 2026-08-17
  checked: Focused regression after applying the same recipient recognizer during query cleanup.
  found: The regression passed with `product_query="LEGO"`, `features=[]`, and `resolved_query="LEGO"`.
  implication: The caveat root cause is fixed at its source without weakening the renderer's grounding behavior.
- timestamp: 2026-08-17
  checked: Full preference, answer, and interactive regression suites after the caveat fix.
  found: All 50 tests passed, including existing unsupported color/size caveats and grounded recommendation behavior.
  implication: The first regression is self-verified and the grounding contract remains intact; typed audio can now be investigated independently.
- timestamp: 2026-08-17
  checked: Complete typed frontend handler and server result construction compared with LiveKit microphone handling.
  found: Typed turns call `synthesize` and retain MP3 bytes in `session_state.answer_audio`, but `external_turn` contains only request ID, transcript, and answer text. `applyExternalTurn` commits the final text immediately and has no audio playback branch. Microphone turns attach a remote LiveKit audio track, and the agent emits `assistant_result` only after `_speak_after_first_frame` observes speech start.
  implication: The typed audio is dropped exactly at the component payload boundary, and typed final-text commitment currently violates the microphone path's first-audio-frame synchronization contract.
- timestamp: 2026-08-17
  checked: TTS type and component transport capabilities.
  found: `synthesize` returns raw MP3 `bytes`, while component props already carry arbitrary JSON dictionaries; an ASCII base64 field is a bounded, lossless transport for the existing short spoken answer.
  implication: No new TTS call or LiveKit injection is needed; the fix belongs only at the typed payload and browser playback seam.
- timestamp: 2026-08-17
  checked: Clarified acceptance behavior for unsupported facets.
  found: Canonical/spoken recommendations must globally omit the stock `does not confirm ...` suffix, speak only positively grounded matched detail, and use candidate/closest-option framing when exact facet evidence is absent.
  implication: Keep the recipient parsing fix, but also change deterministic rendering and answerer instructions rather than preserving caveats for real color/size preferences.
- timestamp: 2026-08-17
  checked: Three updated acceptance regressions before production changes.
  found: All three failed: deterministic reasons emitted the old caveat, natural validation accepted a caveated unsupported size, and the interactive final appended `it does not confirm blue` after positive detail.
  implication: The tests independently cover deterministic rendering, LLM-draft validation, and the end-to-end graph result that must change.
- timestamp: 2026-08-17
  checked: Focused caveat regressions after global positive-only rendering, validation, prompt, and comparison-template changes.
  found: All 12 focused answer, interactive, and response-style tests passed; unsupported sizes/colors are omitted, positive detail remains, and neutral candidate framing is used.
  implication: The clarified caveat behavior is implemented without altering retrieval/ranking; typed audio remains the only unresolved regression.
- timestamp: 2026-08-17
  checked: Typed Streamlit seam regression requiring audio transport before the payload change.
  found: The test errored with `KeyError: audio_base64` even though mocked synthesis returned `b"audio"`.
  implication: This is a direct automated reproduction of the server-to-component drop confirmed by source tracing.
- timestamp: 2026-08-17
  checked: Typed Streamlit seam after adding base64 MP3 transport.
  found: The focused test passed with payload `audio_base64="YXVkaW8="` and `audio_mime="audio/mpeg"`.
  implication: Synthesized bytes now reach the browser component; only autoplay-safe playback and first-frame-gated final commit remain.
- timestamp: 2026-08-17
  checked: Browser typed-audio controller and component event tests.
  found: All 15 Node tests passed, including Send-gesture arming, audio-clock start detection, 1.25-second bounded fallback, one final commit after audio start, one fallback commit on failure, stale-result rejection, and commit acknowledgement.
  implication: The browser logic now shares the microphone path's audio-before-final-text synchronization invariant without duplicating the assistant response.
- timestamp: 2026-08-17
  checked: New-turn concurrency and mixed typed/microphone playback paths.
  found: Typed playback uses its own WebAudio source while microphone playback remains on the LiveKit-attached `agent-audio` element; however, Submit currently arms without explicitly stopping a prior typed source.
  implication: Add an ordered stop-then-arm operation so a newer typed request cancels stale typed playback without touching LiveKit audio.
- timestamp: 2026-08-17
  checked: Typed new-turn cancellation, fallback discoverability, and production frontend build.
  found: All 17 frontend tests passed; a new Send stops prior typed playback before re-arming, pending stale waits settle false, fallback text points to the replay control, and Vite produced the updated distribution bundle successfully.
  implication: Typed concurrency and autoplay fallback are covered; full cross-layer regression verification remains.
- timestamp: 2026-08-17
  checked: Project-wide pytest invocation in the required virtual environment.
  found: The virtual environment does not include pytest (`No module named pytest`).
  implication: Use the repository's existing unittest suites through standard-library discovery; do not install or alter dependencies for verification.
- timestamp: 2026-08-17
  checked: Complete Python unittest discovery using the project virtual environment.
  found: All 127 tests passed.
  implication: Cross-layer grounding, product caps, app state, and LiveKit regressions remain green after both fixes.
- timestamp: 2026-08-17
  checked: Explicit LiveKit microphone synchronization regressions.
  found: Both progress-cue-first-frame and one-aligned-final-answer timing tests passed; their timelines still require audio before `turn_started` and final audio before `assistant_result`.
  implication: The separate typed WebAudio path did not alter microphone/LiveKit audio, progress cues, or exactly-one-final response behavior.
- timestamp: 2026-08-17
  checked: Final frontend build/tests plus source and distribution validation.
  found: Vite rebuilt successfully, all 17 Node tests passed, both changed JavaScript files passed `node --check`, `git diff --check` passed, and the built bundle contains the typed-audio fallback/replay path.
  implication: Source and shipped frontend assets are aligned and mechanically valid.
- timestamp: 2026-08-17
  checked: Exact original caveat reproduction after the final fix.
  found: `LEGO for my kid` now resolves to product query `LEGO` with no features; the recommendation reason is `Catalog evidence notes: Includes astronaut figures and a space rover.` and contains no caveat.
  implication: The reported phrase is removed at both parser and global canonical-rendering layers while retaining only grounded detail.
- timestamp: 2026-08-17
  checked: Exact screenshot feature-detail regression before clause-safe compaction changes.
  found: The `.venv` test failed with actual `Catalog evidence notes: Features a mix of bright, colorful LEGO pieces that allow for open-ended.` instead of the required complete `open-ended play.` clause.
  implication: The remaining edge is reproduced deterministically at `_compact_feature_detail`; the raw 12-word fallback invents a sentence boundary by dropping the final source word.
- timestamp: 2026-08-17
  checked: Clause-safe feature and canonical-opening focused regressions after the minimal changes.
  found: All four focused tests pass: the exact 13-word feature is retained, a 19-word enumeration ends at source punctuation, over-bound punctuation-free evidence falls back to another grounded reason, and a formerly 33-word canonical answer selects a 30-word opening.
  implication: The clause mechanism and canonical word budget are directly verified; independent audit boundaries must be regressed before full verification.
- timestamp: 2026-08-17
  checked: Independent audit of recipient variants, natural caveat validation, and typed/voice lifecycle invalidation.
  found: `my kid please` and `a kid` can escape recipient cleanup; generic negative evidence wording can pass without literal facet terms; restart or voice start can leave an in-flight typed completion eligible to commit and overlap audio.
  implication: Verification remains open until focused RED/GREEN coverage proves each boundary fixed.
- timestamp: 2026-08-17
  checked: Focused audit regressions before production changes.
  found: Recipient tests fail with `features=['my kid please']` and `features=['a kid']`; the natural gate returns the paraphrased sizing caveat instead of `None`; the Node suite fails because no typed-turn epoch guard is exported.
  implication: Each audit finding is independently reproducible and distinguishes the required fixes from the already-green clause/audio transport behavior.
- timestamp: 2026-08-17
  checked: First focused GREEN run for clause, recipient, caveat, and typed lifecycle changes.
  found: All eight typed-audio tests and five of six focused Python tests pass; only `LEGO for a kid` fails with query `LEGO kid` after its feature list is correctly emptied.
  implication: Audio epoch and negative-caveat mechanisms are confirmed; recipient query cleanup needs the original transcript to recover the article-stripped noun safely.
- timestamp: 2026-08-17
  checked: Second focused GREEN run after transcript-derived recipient query cleanup.
  found: All six focused Python cases and all eight typed-audio cases pass, including exact feature retention, grounded fallback, 30-word opening, recipient variants, generic caveat rejection, restart invalidation, and typed-to-voice separation.
  implication: Every newly reported boundary is fixed in isolation; broader regressions are next.

- timestamp: 2026-08-17
  checked: Affected graph and complete frontend regression suites after all fixes.
  found: All 64 affected graph tests and all 19 frontend Node tests pass, including the new recipient, caveat, clause, restart, and typed-to-voice cases.
  implication: Adjacent recommendation and browser-event behavior remains intact after the focused fixes.
- timestamp: 2026-08-17
  checked: Full Python verification using the project virtual environment.
  found: All 131 repository-discovered tests plus all 58 app/voice tests pass; both LiveKit first-frame synchronization regressions are explicitly green.
  implication: Cross-layer catalog, graph, app, TTS, and microphone behavior has no detected regression.
- timestamp: 2026-08-17
  checked: Final frontend production build and mechanical validation.
  found: Vite rebuilt `index-C4o7t9Tx.js`; source and bundle syntax checks pass, the bundle contains the typed-audio fallback/epoch path, and `git diff --check` is clean.
  implication: Shipped frontend assets match the verified source; only real browser speaker/microphone confirmation remains.

## Eliminated

- hypothesis: A 19-word phrase can be treated as short and retained whole while preserving adjacent clause-compaction behavior.
  evidence: The existing Barbie enumeration regression retained all 19 words instead of ending at the first complete `body types,` boundary; reducing the hard bound to 16 made all four focused cases pass.
  timestamp: 2026-08-17T15:07:00-05:00
- hypothesis: Expanding `_RECIPIENT_PHRASE` alone removes both feature and query residue for `for a kid`.
  evidence: The focused test removed `a kid` from features but returned product query `LEGO kid`; `semantic_query` had already removed the article before `_strip_facets` applied the determiner-aware pattern.
  timestamp: 2026-08-17T15:14:00-05:00

## Resolution

- root_cause: The original invalid caveat came from recipient text being parsed as evidence-verifiable product features; determiner/polite variants also survived query cleanup after semantic normalization. Natural-answer validation rejected literal unsupported facets but not paraphrased negative evidence caveats. Typed MP3 was originally omitted from the browser payload, and the later WebAudio synchronization lacked a lifecycle epoch, allowing an awaiting completion to survive restart or voice start. Feature compaction independently raw-cut punctuation-free evidence at 12 words, and canonical opening selection ignored the 30-word combined budget.
- fix: Recipient-only phrases including `my kid please` and `a kid` are excluded from features and removed from the query using original-transcript matches. Natural drafts with generic evidence-failure caveats are rejected. Feature details stay whole through 16 words, use only a source punctuation boundary when longer, or fall through to another grounded reason; canonical openings are budget-filtered. Typed MP3 is transported as base64 and synchronized through a Send-armed WebAudio controller plus a monotonically increasing typed-turn epoch invalidated before restart, voice start, and each new typed submission; commit and acknowledgement require both epoch and request ID.
- verification: The exact `open-ended play` regression and all focused clause, fallback, recipient, caveat, restart, and typed-to-voice tests pass. All 64 affected graph tests, 19 frontend tests, 131 repository-discovered Python tests, and 58 app/voice tests pass. Both explicit LiveKit first-frame tests, Vite production build, source/bundle syntax checks, bundle marker check, and `git diff --check` pass. Real browser speaker/microphone behavior awaits human verification.
- files_changed:
    - graph/preferences.py
    - graph/recommendation.py
    - graph/answer.py
    - graph/response_style.py
    - graph/test_preferences.py
    - graph/test_answer.py
    - graph/test_interactive.py
    - prompts/answerer.md
    - app/main.py
    - app/test_main.py
    - app/livekit_frontend/src/main.js
    - app/livekit_frontend/src/typed_audio.js
    - app/livekit_frontend/test/typed_audio.test.js
    - app/livekit_frontend/dist/index.html
    - app/livekit_frontend/dist/assets/index-C4o7t9Tx.js
