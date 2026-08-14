---
phase: 02-integration
reviewed: 2026-08-14T15:05:20Z
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
  critical: 4
  warning: 4
  info: 0
  total: 8
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-08-14T15:05:20Z  
**Depth:** standard  
**Files Reviewed:** 10  
**Status:** issues_found

## Summary

The scoped MCP adapter, graph selection, Streamlit integration, acceptance harness, tests, captured output, and environment example were reviewed in full. The main shipping risks are evidence-provenance claims that cannot distinguish a real Serper response from recorded fallback data, an acceptance harness that can pass the wrong transcript/product, and UI/TTS behavior that can contradict the evidence or written answer. The scoped unit/UI tests pass in the project virtual environment, but they do not cover these failure modes.

## Narrative Findings (AI reviewer)

### Critical Issues

#### CR-01 [BLOCKER]: Recorded fallback can be presented and accepted as live Serper evidence

**Files:**

- `/Users/jackshi/Desktop/GenAI_Project/app/config.py:14-19`
- `/Users/jackshi/Desktop/GenAI_Project/app/phase2_acceptance.py:62-85`
- `/Users/jackshi/Desktop/GenAI_Project/graph/sample_output.txt:65-84`

**Issue:** `source_mode_label()` treats the mere presence of `SERPER_API_KEY` as proof that evidence came from live Serper, and the acceptance harness treats any completed `web.search` step as the same proof. The server's actual behavior can fall back to recorded fixtures after a live Serper failure while still returning a successful tool call, so both checks can mislabel recorded data as live. The captured sample demonstrates the provenance collapse: its `$21.95`/`3.5` Strongarm result is the recorded fixture value, yet the output calls it a live/current price and gives no recorded-source label. This violates the project's grounding rule and can falsely satisfy the Phase 2 live gate.

**Fix:** Carry explicit response provenance (`live_serper` or `recorded_fixture`) from `web.search` into the graph result/step event. Derive UI labels from that returned provenance, not credential presence. In live acceptance, require `TOOL_MODE=live`, a non-empty key, and `origin == "live_serper"`; fail closed if Serper falls back. Regenerate `sample_output.txt` with an explicit source-mode header, or label it as recorded evidence.

#### CR-02 [BLOCKER]: The acceptance harness can pass a wrong transcript and unrelated evidence

**File:** `/Users/jackshi/Desktop/GenAI_Project/app/phase2_acceptance.py:55-86`

**Issue:** The checks only require a non-empty transcript, at least one completed web call, any price conflict, and any private/live citation. They never assert that ASR produced the canonical Nerf Strongarm request, that the conflict belongs to the Strongarm row, that the expected private document is present, or that cited evidence supports each spoken product claim. A transcription of a different product—or a graph result containing unrelated products and citations—can therefore report `passed: true`. This makes the phase's automated acceptance evidence unreliable.

**Fix:** Make the expected query/product explicit inputs and assert them as one connected evidence chain. For the canonical run, normalize and compare the transcript intent, require `AMZ-7E4E86AE`, require its matched live row to hold the price conflict, and verify every price/rating claim in `answer_text` is backed by that row and its citations. Return diagnostic failures per assertion.

#### CR-03 [BLOCKER]: Missing live evidence is reported as evidence that was not needed

**File:** `/Users/jackshi/Desktop/GenAI_Project/app/main.py:117-127`

**Issue:** When `result.citations` has no live citation, the UI always says, "No live source was needed for this result." A current-price query can require and execute `web.search` but produce no confirmed match, no hits, or an error; `graph/sample_output.txt:27-53` already shows the no-match shape. In that case the caption is false and can make a catalog-only answer look sufficiently current even though the required live evidence was unavailable.

**Fix:** Derive the empty state from step intent/status: distinguish "live lookup not requested," "live lookup failed," and "live lookup completed but no product match was confirmed." For example, inspect `web.search` step events and show a warning for error/no-match cases rather than claiming no live source was needed.

#### CR-04 [BLOCKER]: Spoken and on-screen answers can silently diverge

**File:** `/Users/jackshi/Desktop/GenAI_Project/app/main.py:196-200`

**Issue:** The UI sends `result.answer_text` to `synthesize()`, but that function internally truncates answers over 30 words. `AssistantResult` has no enforced word limit and LLM output is nondeterministic, so an over-length result is displayed in full while only a prefix is spoken. The acceptance harness detects this for its one canonical run, but the production UI does not enforce or surface it. This violates the phase requirement that the displayed and synthesized answer be exactly the same grounded text.

**Fix:** Establish one canonical speech-safe answer before constructing `AssistantResult` and use that exact string for both display and TTS. Enforce the limit deterministically at the graph boundary (with a validation/rewrite step) instead of silently transforming text inside TTS; alternatively, reject an over-length result visibly rather than speaking different content.

### Warnings

#### WR-01 [WARNING]: A transient pipeline failure permanently consumes the recording digest

**File:** `/Users/jackshi/Desktop/GenAI_Project/app/main.py:160-200`

**Issue:** `audio_digest` is stored before transcription, graph execution, and TTS complete. If any of those stages fails, a rerun with the same `st.audio_input` value sees the digest as already processed and skips the failed work. The UI tells the user to retry after STT/graph failure, but the same recording cannot actually be retried; the user must create a new recording.

**Fix:** Commit the digest only after the intended processing stage succeeds, or clear it in every failure path. Persist explicit per-stage state so STT, graph, and TTS can each be retried without rerecording.

#### WR-02 [WARNING]: The step-log heading counts failed and skipped events as completed

**File:** `/Users/jackshi/Desktop/GenAI_Project/app/main.py:97-101`

**Issue:** The expander title uses `len(result.steps)` but labels that number "completed steps." Error and skipped events are included in the same count. During degraded retrieval this produces a misleading success summary even though the table below contains failures.

**Fix:** Either call the value "step events" or count only `step.status == "completed"` and separately surface error/skipped counts.

#### WR-03 [WARNING]: Schema-validation failures escape the MCP boundary without the promised tool context

**File:** `/Users/jackshi/Desktop/GenAI_Project/graph/tools_mcp.py:70-77`

**Issue:** Transport errors and invalid JSON are converted to `RuntimeError` naming the tool, but `_decode()` executes outside that wrapping path. A syntactically valid response with the wrong schema raises a raw Pydantic validation error rather than the adapter's documented `RuntimeError("rag.search failed: ...")`/`RuntimeError("web.search failed: ...")`. This makes boundary behavior inconsistent and complicates diagnosis by callers other than the current broad retriever catch.

**Fix:** Wrap payload extraction and `_decode()` together in a tool-aware helper, preserving the original exception as the cause. Add malformed-but-valid JSON cases for both tool result types.

#### WR-04 [WARNING]: Core one-session lifecycle behavior is bypassed by the MCP tests

**File:** `/Users/jackshi/Desktop/GenAI_Project/graph/test_tools_mcp.py:50-68`

**Issue:** Every adapter test injects `_session` directly and never enters `MCPTools` as an async context manager. Consequently the tests cannot detect regressions in subprocess creation, `ClientSession.initialize()`, sharing one session across multiple calls, or closing the stack exactly once—the core Phase 2 lifecycle contract. Passing tests therefore provide no evidence for the most important new behavior.

**Fix:** Mock `stdio_client`, `ClientSession`, and `AsyncExitStack` at the public context-manager boundary. Assert one initialization, multiple calls on the same fake session, and exactly one close on both successful turns and initialization/graph exceptions.

## Verification

- `.venv/bin/python -m unittest -v graph.test_tools_mcp app.test_config app.test_main` — 13 tests passed.
- The same command under the system Python failed to import optional project dependencies (`mcp`, `langgraph`); this was an interpreter/environment mismatch, not counted as a source finding.
- No source files were modified.

---

_Reviewed: 2026-08-14T15:05:20Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: standard_
