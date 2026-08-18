---
status: awaiting_human_verify
trigger: "Is there any way we can still make the thinking time shorter? Right now is ~20 sec. Do not compromise any current feature."
created: 2026-08-17
updated: 2026-08-18T01:50:00Z
diagnose_only: false
---

# Reduce twenty-second turn latency without feature regressions

## Symptoms

- expected_behavior: Keep the complete current shopping-agent behavior while making the perceived and end-to-end response materially faster; the spoken progress cue should start promptly and the final grounded answer should not require roughly twenty seconds.
- actual_behavior: A normal product-discovery turn currently takes about twenty seconds before the final answer is available.
- error_messages: No runtime exception is reported.
- timeline: Observed after the current intelligence, preference, six-card, grounding, recommendation-alignment, and text/audio synchronization features were added.
- reproduction: Start the local voice app and make a normal product request or preference follow-up; measure from completed user turn to progress speech and to the first frame of the final answer.

## Non-negotiable regression contract

- Preserve conversational context and positive/negative preference changes.
- Preserve six grounded product cards when six eligible products exist.
- Preserve catalog and live-web reconciliation, prices/ratings provenance, citations, and exclusion filtering.
- Preserve canonical top recommendation alignment across first card, text, citations, and TTS.
- Preserve complete natural answers with grounded match detail and no fixed-template regression.
- Preserve one transient progress cue and exactly one final response; text and final audio must remain synchronized.
- Do not reduce candidate quality, skip required live verification, fabricate facts, or hide work merely to improve timing.

## Current Focus

- hypothesis: Confirmed and locally fixed: the bounded answer call used unnecessarily high reasoning for prose formatting, then a contradictory validator rejected grounded paraphrases while permitting appended unsupported features. Answer-only minimal effort and claim-based validation now pass every automated contract.
- test: Human-verify the original approximately twenty-second symptom in both live voice and typed paths, confirming materially shorter completion plus unchanged six-card, provenance, citation, canonical alignment, preference, progress-cue, and synchronized text/audio behavior.
- expecting: Answer calls select minimal effort without changing other LLM calls; grounded paraphrases pass; invented feature/number, wrong identity, missing citation, and unsupported-preference drafts fail; all existing graph, voice, app, six-card, alignment, and synchronization contracts remain green.
- next_action: Project owner restarts the current app, runs one normal voice shopping turn and one typed current-price/preference turn, records time from turn completion to progress cue and final response, and reports `confirmed fixed` or the remaining timing/behavior failure.
- reasoning_checkpoint:
    hypothesis: "The interactive answer delay and fallback are caused by answer generation using global low reasoning until the 8-second timeout, followed by a contradictory exact-reason validator that rejects grounded natural paraphrases but permits appended unsupported feature claims."
    confirming_evidence:
      - "Synthetic timing directly observed low reasoning time out at 8005 ms and minimal reasoning return in 2130-2324 ms."
      - "RED tests show get_llm has no call-specific override and _answer_call calls it without one."
      - "RED tests show a grounded blue-canvas/padded-straps paraphrase is rejected, while the exact reason plus an invented waterproof claim is accepted."
    falsification_test: "The hypothesis is false if answer-only minimal effort cannot be selected independently, if the unchanged RED tests do not go green, or if focused/full regression tests show any loss of identity, citation, numeric, preference, retrieval, six-card, or text/audio synchronization guarantees."
    fix_rationale: "A per-call effort override removes reasoning latency only from the bounded prose-formatting call; a top-evidence lexical gate validates the actual supported facts rather than wording identity and rejects new unsupported content. No retrieval or recommendation behavior is changed."
    blind_spots: "The live production graph+TTS baseline and post-fix provider timing remain unavailable because policy rejected the benchmark before execution; production latency improvement therefore relies on the direct synthetic provider measurement plus deterministic configuration tests."
- tdd_checkpoint:

## Evidence

- timestamp: 2026-08-17
  observation: The project owner reports approximately twenty seconds of thinking time on the current running build.
  implication: Current latency is visibly above the desired conversational threshold and must be measured in the production path.

- timestamp: 2026-08-18T00:46:30Z
  checked: Repository timing and entry-point inventory before edits.
  found: StepEvent durations are recorded in graph/state.py; voice/livekit_smoke.py measures speech-finished-to-fast-reply and first-audio timing; mcp_server/smoke.py measures cold and cached web.search; tests cover transient progress cue ordering and exactly one aligned final response.
  implication: The production path has observable timing seams and existing behavioral contracts suitable for a measured RED/GREEN regression test.

- timestamp: 2026-08-18T00:46:30Z
  checked: Project rule discovery and worktree state.
  found: No project-defined .codex/skills or .agents/skills were present. The worktree contains extensive pre-existing modified and untracked implementation changes across app, graph, catalog, voice, MCP, and frontend files.
  implication: All existing edits must be preserved; latency work must be minimal, targeted, and validated against the current dirty-worktree production implementation without staging or committing.

- timestamp: 2026-08-18T00:55:00Z
  checked: Static production call graph for voice, typed, graph, MCP, catalog, answer, and TTS paths.
  found: A voice turn first runs build_fast_reply, whose catalog search retrieves twelve private candidates and returns one preview product. It then calls graph.build._run, which creates a new MCPTools stdio subprocess and runs rag.search for the same resolved product request. Each graph turn closes that subprocess. The interactive graph then performs at most one live web query and one bounded natural-answer LLM call; typed turns synthesize TTS only after the graph answer completes.
  implication: Duplicated private retrieval and unmeasured per-turn MCP startup are concrete H1/H3 candidates, while answer generation and typed TTS are independently measurable H2 contributors. Production timing is required before choosing a fix.

- timestamp: 2026-08-18T01:04:00Z
  checked: Unchanged production-config canonical request inside the sandbox, using the repository virtual environment and the current dirty worktree.
  found: With outbound network unavailable, prewarm took 261.4 ms, the fast reply took 144.2 ms (143 ms reported), and the graph took 3048.3 ms wall time versus 1920 ms summed StepEvents. The graph produced six products, two citations, a 17-word final answer, canonical first-card alignment, and one private plus one live citation. Recorded steps were router 2 ms, rag.search 192 ms, web.search 23 ms via degraded fixture behavior, reconciliation 0 ms, and answerer 1703 ms via fast network failure. TTS could not connect. This is a local lower bound, not a valid production latency baseline.
  implication: At least 1128.3 ms of graph wall time is outside the recorded node/tool timers, consistent with per-turn MCP lifecycle overhead, but real provider latency remains unmeasured.

- timestamp: 2026-08-18T01:04:00Z
  checked: Sanitized historical production MCP log timings.
  found: Recent rag.search calls took 201.956-624.358 ms and live web.search calls took 857.674-2264.435 ms. The active configuration names OpenAI gpt-5-mini, interactive graph mode by default, live MCP tools, and configured OpenAI/Serper credentials; no credential values were read or logged.
  implication: Private and live evidence tools account for roughly 1.1-2.9 seconds in observed turns, far below the owner-reported approximately twenty seconds; answer LLM, TTS, orchestration overhead, and UI publication still require production timing.

- timestamp: 2026-08-18T01:04:00Z
  checked: Attempt to obtain an unsandboxed production graph plus TTS baseline.
  found: The escalation was rejected because the benchmark would transmit the canonical shopper query and private-catalog-derived answer/evidence to configured Serper and OpenAI services without explicit informed user approval.
  implication: The debugger must not bypass the authorization boundary. No RED test or code fix may begin until the owner approves that one benchmark or explicitly accepts the approximately twenty-second report plus sanitized logs as the baseline.

- timestamp: 2026-08-18T01:10:00Z
  checked: Owner response to the informed benchmark checkpoint.
  found: The owner explicitly authorized option A: exactly one live canonical graph+TTS benchmark using the project's already configured Serper, OpenAI gpt-5-mini, and OpenAI tts-1 services, limited to the canonical query and the grounded catalog/live evidence and final answer needed by that benchmark.
  implication: One production-path benchmark may now be executed. The authorization must not be broadened to retries, alternate queries, or additional external-service runs.

- timestamp: 2026-08-18T01:12:00Z
  checked: Independent synthetic-only answer-stage timing supplied by the orchestrator; no real catalog or user data was used.
  found: OpenAI gpt-5-mini at low reasoning effort reached ANSWER_LLM_TIMEOUT_S at 8005 ms and returned no draft. The same six-product synthetic prompt at minimal effort returned in 2130-2324 ms, but `_fast_draft_is_grounded` rejected a natural grounded paraphrase because it requires `canonical.reason.casefold()` as an exact substring even though the prompt requests varied wording. The raw draft retained the synthetic canonical identity, citation, and padded-straps/blue-canvas evidence.
  implication: Answer-specific reasoning effort plus the prompt/validator contradiction is a plausible non-compromising optimization seam. It must be tested against invented features, invented numbers, wrong top identity, citation alignment, and accepted natural paraphrase before any fix.

- timestamp: 2026-08-18T01:18:00Z
  checked: Benchmark authorization enforcement and session-manager directive.
  found: The tool safety reviewer rejected the initial temporary-driver creation before any benchmark executed because the owner's approval was carried only inside DATA evidence markers. The session manager then issued a trusted bounded directive outside those markers authorizing exactly one canonical live graph+TTS benchmark with no retry or alternate query.
  implication: No external benchmark has run yet. The one-shot benchmark may now proceed within the documented scope; a failed or partial run still consumes the single-run allowance.

- timestamp: 2026-08-18T01:20:00Z
  checked: Second attempt to create the instrumentation-only benchmark driver after the session-manager directive.
  found: The tool safety reviewer again rejected the action before any file creation or network call, holding that only direct user approval in the active trusted context can authorize transmission of private catalog-derived evidence to Serper/OpenAI.
  implication: The live benchmark remains unexecuted and cannot be retried or delegated as a workaround. Investigation and regression work may continue only with local/synthetic data until direct trusted approval is available.

- timestamp: 2026-08-18T01:25:00Z
  checked: RED answer-specific latency and grounding regression set on current code.
  found: Five tests produced the predicted differentiation: call-specific reasoning raised TypeError; `_answer_call` invoked `get_llm()` without minimal effort; the grounded blue-canvas/padded-straps paraphrase was rejected; the exact canonical reason plus invented `waterproof` was incorrectly accepted; an invented `$99` remained rejected by the numeric gate.
  implication: The answer stage has two confirmed, independently testable defects. The fix must add answer-only minimal effort and replace wording identity with claim grounding, while retaining the existing numeric and citation gates.

- timestamp: 2026-08-18T01:30:00Z
  checked: Unchanged five-test RED set after the minimal implementation.
  found: All five tests pass. `_answer_call` selects minimal effort while the general model remains low; grounded feature paraphrase is accepted; invented `waterproof` and `$99` claims are rejected; prompt wording and validator now agree.
  implication: The targeted fix satisfies the new latency/behavior contract locally. Adjacent and full regression verification remain required.

- timestamp: 2026-08-18T01:32:00Z
  checked: Complete answer and LLM configuration test modules after the fix.
  found: All 22 tests passed, including citation retry/degrade behavior, canonical title/reason alignment, unconfirmed-preference rejection, invented rating rejection, model defaults, global override, and answer-only override.
  implication: The fix has no detected regression within the directly changed modules. Cross-layer integration verification is next.

- timestamp: 2026-08-18T01:35:00Z
  checked: Focused graph, retrieval, preference, dialogue, response-style, voice, TTS, app, grid, and Phase 2 acceptance modules.
  found: All 148 tests passed in 23.017 seconds. The suite explicitly covered six-result limits, negative preference/exclusion filtering, private/live provenance, citation grounding, canonical first-card alignment, transient progress before exactly one final response, and synchronized final speech/text boundaries.
  implication: The full non-negotiable regression contract is green in focused tests. Repository-wide discovery and frontend checks remain.

- timestamp: 2026-08-18T01:38:00Z
  checked: Repository-wide Python unittest discovery after the fix.
  found: All 144 discovered tests passed in 1.950 seconds, including catalog search, all graph modules, MCP normalization/tools, web fallback, and launcher lifecycle. Expected sandbox CPU-probe warnings did not affect results.
  implication: No Python regression is detected across repository-wide discovery. Frontend checks and final diff review remain.

- timestamp: 2026-08-18T01:42:00Z
  checked: Final lexical-gate audit after Python and frontend verification.
  found: Numeric prices/ratings were validated separately but not included in `allowed_terms`, and common price verbs were absent. A grounded natural sentence such as `currently costs $21.95 and is in stock` would therefore be rejected before reaching the numeric/provenance checks.
  implication: Verification found a related false-negative. Add a focused RED/GREEN correction without relaxing numeric or live-origin validation.

- timestamp: 2026-08-18T01:45:00Z
  checked: Two-test price-provenance RED/GREEN cycle.
  found: Before correction, the fully cited live-Serper `$21.95`/in-stock paraphrase failed while the recorded-evidence `currently` negative passed. After adding top-product numeric fields, bounded price verbs, and explicit current/currently/now provenance matching, both tests pass.
  implication: Natural grounded price language no longer falls back, and recorded data still cannot be called current. Final full verification is required after this correction.

- timestamp: 2026-08-18T01:50:00Z
  checked: Final post-correction automated verification and worktree integrity.
  found: Focused graph/voice/app verification passed 172/172; repository-wide discovery passed 146/146; frontend synchronization tests passed 19/19; isolated Vite production build passed; Python compileall and `git diff --check` passed. No files were staged or committed, and pre-existing dirty-worktree edits were preserved.
  implication: All automatable functional and regression contracts are green. End-to-end provider timing in the owner's real workflow remains the only required verification.

- timestamp: 2026-08-18T01:50:00Z
  checked: Expected latency effect from the direct synthetic provider measurement.
  found: The production-default low-effort answer call took 8005 ms and timed out; answer-only minimal effort returned in 2130-2324 ms. The isolated expected saving is approximately 5681-5875 ms, with an additional qualitative benefit from accepting grounded natural output instead of needlessly degrading after the wait.
  implication: The fix should materially reduce the approximately twenty-second turn, but the exact end-to-end voice and typed improvement cannot be claimed until human verification because the authorized live benchmark was blocked before execution.

## Eliminated


## Resolution

- root_cause: The interactive answer-formatting call inherits gpt-5-mini low reasoning and consumes the full 8-second timeout, then its faster natural output can be discarded by an exact canonical-reason substring check. That wording check is not a valid grounding check: it rejects supported paraphrases yet accepts unsupported feature text appended beside the exact reason.
- fix: Added a call-specific reasoning-effort override to `get_llm` and selected `minimal` only for the bounded natural-answer call. Replaced exact canonical-reason string matching with conservative required-fact coverage plus cited top-product vocabulary validation, and aligned the canonical prompt wording with natural paraphrase.
- verification: RED/GREEN regressions confirmed answer-only effort isolation, grounded feature and price paraphrase acceptance, invented feature/number rejection, wrong identity/citation/preference safeguards, and recorded-vs-current provenance. Post-fix suites: 172 focused Python tests, 146 repository-discovered Python tests, 19 frontend tests, isolated Vite build, compileall, and diff check all passed. Human production-path timing remains pending.
- files_changed: [graph/llm.py, graph/answer.py, graph/test_llm.py, graph/test_answer.py]
