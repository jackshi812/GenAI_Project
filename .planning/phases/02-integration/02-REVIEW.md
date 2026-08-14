---
phase: 02-integration
reviewed: 2026-08-14T15:05:20Z
remediation_reviewed: 2026-08-14T15:15:14Z
cr02_rechecked: 2026-08-14T15:19:27Z
cr02_typed_rechecked: 2026-08-14T15:21:18Z
cr02_final_rechecked: 2026-08-14T15:23:26Z
cr02_bounded_verified: 2026-08-14T15:25:27Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - graph/tools_mcp.py
  - graph/test_tools_mcp.py
  - app/config.py
  - app/test_config.py
  - app/test_main.py
  - app/phase2_acceptance.py
  - graph/build.py
  - graph/sample_output.txt
  - app/main.py
  - .env.example
findings:
  critical: 1
  warning: 2
  info: 0
  total: 3
remediation:
  original_findings: 8
  resolved: 5
  partially_resolved: 1
  open_unchanged: 2
remediation_files_reviewed:
  - contracts.py
  - app/config.py
  - app/main.py
  - app/phase2_acceptance.py
  - app/test_config.py
  - app/test_phase2_acceptance.py
  - voice/tts.py
  - voice/test_tts.py
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-08-14T15:05:20Z  
**Depth:** standard  
**Files Reviewed:** 10  
**Status:** issues_found

## Summary

The scoped MCP adapter, graph selection, Streamlit integration, acceptance harness, tests, captured output, and environment example were reviewed in full. After remediation, the remaining active blocker is cross-owner evidence provenance (CR-01); the two active warnings concern Ginger-owned MCP boundary/lifecycle coverage. CR-02's bounded acceptance-validation scope and the four Jack-owned UI/TTS findings are resolved.

## Remediation Status — 2026-08-14T15:15:14Z

Jack's current uncommitted changes in `contracts.py`, `app/`, and `voice/` were re-reviewed against CR-01 through CR-04 and WR-01/WR-02. Five findings are resolved, CR-01 remains partially resolved, and the two original Ginger-owned warnings remain open and unchanged. Frontmatter finding counts now describe the three active findings; the original review contained eight.

| Finding | Status | Re-review result |
|---|---|---|
| CR-01 | **PARTIALLY RESOLVED — BLOCKER OPEN** | The app now derives labels from `WebResult.origin` and acceptance requires `live_serper`, so Jack's paths fail closed. The live MCP server still emits no origin, and the captured graph output still calls recorded values live. |
| CR-02 | **RESOLVED** | Under the explicitly bounded price/rating/availability acceptance scope, all 12 tests pass and the contradictory second price pair, `rating came in at 10.95`, and `backordered` probes each reject through the intended typed check. Semantic grounding beyond this bounded harness remains the graph Critic's responsibility. |
| CR-03 | **RESOLVED** | `live_evidence_notice()` distinguishes no lookup, failed lookup, completed/no-match, and incomplete lookup; `app/main.py` renders the appropriate caption/warning. |
| CR-04 | **RESOLVED** | The app canonicalizes the displayed `answer_text` before storing it, and `synthesize()` now sends that exact text or rejects an uncapped caller. |
| WR-01 | **RESOLVED** | The recording digest is committed only after graph and TTS success, leaving the same recording retryable after STT, graph, or TTS failure. |
| WR-02 | **RESOLVED** | The step header now reports total events, completed events, and errors separately. |
| WR-03 | **OPEN — unchanged** | No Ginger-owned MCP adapter changes were part of this remediation. |
| WR-04 | **OPEN — unchanged** | No Ginger-owned lifecycle-test changes were part of this remediation. |

### Exact remaining work

- **Austin — CR-01:** In `mcp_server/web_search.py`, attach `origin="live_serper"` only when `_call_serper()` actually supplied the normalized response, and `origin="recorded_fixture"` for no-key replay and live-error fallback. Preserve the origin in cached results. Add coverage for live success, no-key replay, live failure followed by replay, and cache hits. Emitting this field from `mcp_server/server.py` then works automatically because it serializes the normalized result dictionaries.
- **Ginger — CR-01:** After Austin's origin field lands, verify `graph/tools_mcp.py` preserves it through `_decode`, add an assertion to `graph/test_tools_mcp.py`, update `graph/smoke.py` to print evidence origin/source mode, and regenerate `graph/sample_output.txt`. The current `$21.95`/`3.5` Strongarm sample is recorded fallback evidence but is still labeled live/current.
- **Ginger — WR-03:** Wrap `_payload()` and `_decode()` together so valid JSON with an invalid schema raises a tool-named `RuntimeError`; add malformed-schema tests for both tools.
- **Ginger — WR-04:** Add context-manager lifecycle tests proving one initialization, reuse of one session for all calls, and exactly one close on success and exception paths.

## Narrative Findings (AI reviewer)

### Critical Issues

#### CR-01 [BLOCKER]: Recorded fallback can be presented and accepted as live Serper evidence

**Remediation status (2026-08-14T15:15:14Z): PARTIALLY RESOLVED — remains an active blocker.** Jack's app and acceptance paths now fail closed on `origin`, but Austin's server does not yet populate it and Ginger's captured output remains misleading.

**Files:**

- `/Users/jackshi/Desktop/GenAI_Project/app/config.py:14-19`
- `/Users/jackshi/Desktop/GenAI_Project/app/phase2_acceptance.py:62-85`
- `/Users/jackshi/Desktop/GenAI_Project/graph/sample_output.txt:65-84`

**Issue:** `source_mode_label()` treats the mere presence of `SERPER_API_KEY` as proof that evidence came from live Serper, and the acceptance harness treats any completed `web.search` step as the same proof. The server's actual behavior can fall back to recorded fixtures after a live Serper failure while still returning a successful tool call, so both checks can mislabel recorded data as live. The captured sample demonstrates the provenance collapse: its `$21.95`/`3.5` Strongarm result is the recorded fixture value, yet the output calls it a live/current price and gives no recorded-source label. This violates the project's grounding rule and can falsely satisfy the Phase 2 live gate.

**Fix:** Carry explicit response provenance (`live_serper` or `recorded_fixture`) from `web.search` into the graph result/step event. Derive UI labels from that returned provenance, not credential presence. In live acceptance, require `TOOL_MODE=live`, a non-empty key, and `origin == "live_serper"`; fail closed if Serper falls back. Regenerate `sample_output.txt` with an explicit source-mode header, or label it as recorded evidence.

#### CR-02 [BLOCKER]: The acceptance harness can pass a wrong transcript and unrelated evidence

**Remediation status (2026-08-14T15:25:27Z): RESOLVED within the documented bounded scope.** All 12 acceptance tests pass. Independent replays of the contradictory second price pair, `rating came in at 10.95`, and `backordered` each returned `passed: false` through `price_sources_grounded`, `rating_claims_grounded`, and `availability_claims_grounded`, respectively. Broader natural-language semantic grounding remains the graph Critic's gate by explicit review scope.

**File:** `/Users/jackshi/Desktop/GenAI_Project/app/phase2_acceptance.py:55-86`

**Issue:** The checks only require a non-empty transcript, at least one completed web call, any price conflict, and any private/live citation. They never assert that ASR produced the canonical Nerf Strongarm request, that the conflict belongs to the Strongarm row, that the expected private document is present, or that cited evidence supports each spoken product claim. A transcription of a different product—or a graph result containing unrelated products and citations—can therefore report `passed: true`. This makes the phase's automated acceptance evidence unreliable.

**Fix:** Make the expected query/product explicit inputs and assert them as one connected evidence chain. For the canonical run, normalize and compare the transcript intent, require `AMZ-7E4E86AE`, require its matched live row to hold the price conflict, and verify every price/rating claim in `answer_text` is backed by that row and its citations. Return diagnostic failures per assertion.

#### CR-03 [BLOCKER]: Missing live evidence is reported as evidence that was not needed

**Remediation status (2026-08-14T15:15:14Z): RESOLVED.** `app/config.py:38-50` now returns distinct no-request, failure, completed/no-match, and incomplete messages; `app/main.py:128-134` renders them, and focused tests cover the main branches.

**File:** `/Users/jackshi/Desktop/GenAI_Project/app/main.py:117-127`

**Issue:** When `result.citations` has no live citation, the UI always says, "No live source was needed for this result." A current-price query can require and execute `web.search` but produce no confirmed match, no hits, or an error; `graph/sample_output.txt:27-53` already shows the no-match shape. In that case the caption is false and can make a catalog-only answer look sufficiently current even though the required live evidence was unavailable.

**Fix:** Derive the empty state from step intent/status: distinguish "live lookup not requested," "live lookup failed," and "live lookup completed but no product match was confirmed." For example, inspect `web.search` step events and show a warning for error/no-match cases rather than claiming no live source was needed.

#### CR-04 [BLOCKER]: Spoken and on-screen answers can silently diverge

**Remediation status (2026-08-14T15:15:14Z): RESOLVED.** `app/main.py:195-199` stores the speech-capped text as the displayed result, while `voice/tts.py:33-53` synthesizes exactly its input and rejects uncapped text. The new TTS boundary tests cover exact forwarding and rejection.

**File:** `/Users/jackshi/Desktop/GenAI_Project/app/main.py:196-200`

**Issue:** The UI sends `result.answer_text` to `synthesize()`, but that function internally truncates answers over 30 words. `AssistantResult` has no enforced word limit and LLM output is nondeterministic, so an over-length result is displayed in full while only a prefix is spoken. The acceptance harness detects this for its one canonical run, but the production UI does not enforce or surface it. This violates the phase requirement that the displayed and synthesized answer be exactly the same grounded text.

**Fix:** Establish one canonical speech-safe answer before constructing `AssistantResult` and use that exact string for both display and TTS. Enforce the limit deterministically at the graph boundary (with a validation/rewrite step) instead of silently transforming text inside TTS; alternatively, reject an over-length result visibly rather than speaking different content.

### Warnings

#### WR-01 [WARNING]: A transient pipeline failure permanently consumes the recording digest

**Remediation status (2026-08-14T15:15:14Z): RESOLVED.** `app/main.py:166-181,210-216` holds the digest pending and commits it only after TTS succeeds, so the unchanged recording retries after any earlier failure.

**File:** `/Users/jackshi/Desktop/GenAI_Project/app/main.py:160-200`

**Issue:** `audio_digest` is stored before transcription, graph execution, and TTS complete. If any of those stages fails, a rerun with the same `st.audio_input` value sees the digest as already processed and skips the failed work. The UI tells the user to retry after STT/graph failure, but the same recording cannot actually be retried; the user must create a new recording.

**Fix:** Commit the digest only after the intended processing stage succeeds, or clear it in every failure path. Persist explicit per-stage state so STT, graph, and TTS can each be retried without rerecording.

#### WR-02 [WARNING]: The step-log heading counts failed and skipped events as completed

**Remediation status (2026-08-14T15:15:14Z): RESOLVED.** `app/main.py:97-105` now distinguishes event count, completed count, and error count.

**File:** `/Users/jackshi/Desktop/GenAI_Project/app/main.py:97-101`

**Issue:** The expander title uses `len(result.steps)` but labels that number "completed steps." Error and skipped events are included in the same count. During degraded retrieval this produces a misleading success summary even though the table below contains failures.

**Fix:** Either call the value "step events" or count only `step.status == "completed"` and separately surface error/skipped counts.

#### WR-03 [WARNING]: Schema-validation failures escape the MCP boundary without the promised tool context

**Remediation status (2026-08-14T15:15:14Z): OPEN — unchanged; Ginger-owned.**

**File:** `/Users/jackshi/Desktop/GenAI_Project/graph/tools_mcp.py:70-77`

**Issue:** Transport errors and invalid JSON are converted to `RuntimeError` naming the tool, but `_decode()` executes outside that wrapping path. A syntactically valid response with the wrong schema raises a raw Pydantic validation error rather than the adapter's documented `RuntimeError("rag.search failed: ...")`/`RuntimeError("web.search failed: ...")`. This makes boundary behavior inconsistent and complicates diagnosis by callers other than the current broad retriever catch.

**Fix:** Wrap payload extraction and `_decode()` together in a tool-aware helper, preserving the original exception as the cause. Add malformed-but-valid JSON cases for both tool result types.

#### WR-04 [WARNING]: Core one-session lifecycle behavior is bypassed by the MCP tests

**Remediation status (2026-08-14T15:15:14Z): OPEN — unchanged; Ginger-owned.**

**File:** `/Users/jackshi/Desktop/GenAI_Project/graph/test_tools_mcp.py:50-68`

**Issue:** Every adapter test injects `_session` directly and never enters `MCPTools` as an async context manager. Consequently the tests cannot detect regressions in subprocess creation, `ClientSession.initialize()`, sharing one session across multiple calls, or closing the stack exactly once—the core Phase 2 lifecycle contract. Passing tests therefore provide no evidence for the most important new behavior.

**Fix:** Mock `stdio_client`, `ClientSession`, and `AsyncExitStack` at the public context-manager boundary. Assert one initialization, multiple calls on the same fake session, and exactly one close on both successful turns and initialization/graph exceptions.

## Verification

- `.venv/bin/python -m unittest -v app.test_phase2_acceptance` — all 12 bounded acceptance tests passed.
- Independent final probes: contradictory second price pair, `rating came in at 10.95`, and `backordered` — all correctly returned `passed: false` through their corresponding typed checks; CR-02 resolved.
- `.venv/bin/python -m unittest -v app.test_phase2_acceptance` — 9 focused tests passed after source/rating/availability updates.
- Previously reported swapped-only price, `rating was 10.95`, and `sold out` probes — all correctly returned `passed: false`.
- Equivalent probes containing a correct pair plus a contradictory reversed price pair, `rating came in at 10.95`, and `backordered` against `In stock` evidence — all incorrectly returned `passed: true`; CR-02 remains open and counts are unchanged.
- `.venv/bin/python -m unittest -v app.test_phase2_acceptance` — 6 focused tests passed after typed claim validation.
- Exact residual `live rating is 10.95` with `canonical_live.rating=None` — correctly returned `passed: false` via `rating_claims_grounded`.
- Equivalent probes `Catalog price $10.95; live price $13.99.`, `live rating was 10.95`, and `sold out` against `In stock` evidence — all incorrectly returned `passed: true`; CR-02 remains open and counts are unchanged.
- `.venv/bin/python -m unittest -v app.test_phase2_acceptance` — 5 focused tests passed.
- Independent probes for invented rating `5.0`, wrong `out of stock` availability, unrelated `99`, and `$113.99` substring — all correctly returned `passed: false`.
- Earlier field-confusion probe `Catalog price $13.99, live price $10.95, live rating 10.95.` — now correctly rejected by typed rating validation.
- `.venv/bin/python -m unittest -v app.test_config app.test_phase2_acceptance app.test_main voice.test_tts` — 11 remediation-focused tests passed.
- `.venv/bin/python -m unittest -v graph.test_tools_mcp graph.test_answer` — 11 affected graph/MCP regression tests passed.
- Original verification: `.venv/bin/python -m unittest -v graph.test_tools_mcp app.test_config app.test_main` — 13 tests passed.
- The same command under the system Python failed to import optional project dependencies (`mcp`, `langgraph`); this was an interpreter/environment mismatch, not counted as a source finding.
- No source files were modified by the reviewer; only this report was updated.

---

_Reviewed: 2026-08-14T15:05:20Z_  
_Remediation reviewed: 2026-08-14T15:15:14Z_
_CR-02 rechecked: 2026-08-14T15:19:27Z_
_CR-02 typed rechecked: 2026-08-14T15:21:18Z_
_CR-02 final rechecked: 2026-08-14T15:23:26Z_
_CR-02 bounded verified: 2026-08-14T15:25:27Z_
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: standard_
