---
status: resolved
trigger: "Every response starts with 'Oh', sentence structure is fixed, and 'I don't like them' returns an unrelated product"
created: 2026-08-16
updated: 2026-08-16
diagnose_only: false
---

# Repetitive replies and broken rejection follow-up

## Symptoms

- expected_behavior: Recommendations use natural, varied grounded language. A rejection such as "I don't like them" acknowledges the previous recommendations and asks what should change before searching again.
- actual_behavior: Product replies repeatedly start with "Oh, I found" and use the same sentence structure. "I don't like them" is searched as a product query and returns "Don't Go In There."
- error_messages: No exception is shown.
- timeline: Began after the recent warm-response helper was introduced.
- reproduction: Receive product results, then submit "I don't like them."

## Current Focus

- hypothesis: Confirmed — response helpers hardcoded one opener, and the stateless query normalizer treated contraction residue from a rejection as a product name.
- test: Unit, graph, Streamlit, and voice regressions for varied grounded wording and rejection turns that make zero retrieval calls.
- expecting: No universal "Oh" prefix; rejection is classified as feedback, preserves previous results, retains the budget, and asks one useful refinement question.
- next_action: Resolved and verified.
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- timestamp: 2026-08-16T17:55:00Z
  observation: Screenshot shows "I don't like them" producing a web result titled "Don't Go In There" and the nonsensical phrase "matches your don't request."
- timestamp: 2026-08-16T17:56:00Z
  observation: catalog_recommendation(), web_recommendation(), and their compact fallbacks all hardcode "Oh, I found".
- timestamp: 2026-08-16T17:56:00Z
  observation: contextualize_followup() carries only a budget. semantic_query() leaves "don't them", which is classified as a specific product and escalated to web search.
- timestamp: 2026-08-16T17:59:00Z
  observation: The fixed interactive graph classifies "I don't like them" as preference refinement, makes zero rag.search/web.search calls, and retains prior products and citations.

## Eliminated

- hypothesis: The web provider invented the response wording.
  reason: The application generates the sentence locally in graph/response_style.py after retrieval.

## Resolution

- root_cause: Warm-response helpers hardcoded "Oh, I found" and one clause order. The dialogue handoff stored only a one-turn pending budget, so rejection language was normalized as the product query "don't them" and sent to web search.
- fix: Added deterministic rejection/refinement intent handling before retrieval, prior-result and active-budget dialogue context for typed and voice turns, retained evidence cards during refinement, and stable context-dependent recommendation structures with no universal opener. Updated the LLM Answerer prompt to avoid catchphrases.
- verification: 54 core project tests and 43 app/voice tests pass; the exact two-turn Streamlit regression verifies retained products and budget with no new search; Streamlit health endpoint returns ok.
- files_changed: graph/response_style.py, graph/fast_reply.py, graph/interactive.py, graph/nodes.py, graph/retriever.py, graph/answer.py, graph/build.py, graph/state.py, voice/livekit_agent.py, app/config.py, app/main.py, prompts/answerer.md, and regression tests.
