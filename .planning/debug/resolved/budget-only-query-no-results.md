---
status: resolved
trigger: "Budget-only shopping queries return no grounded product results"
created: 2026-08-16
updated: 2026-08-16
diagnose_only: true
---

# Budget-only query returns no results

## Symptoms

- expected_behavior: A broad request such as "What is something I can buy under 20 bucks" returns up to three grounded catalog products priced below $20.
- actual_behavior: The assistant says it could not find a grounded product, and the results panel is empty.
- error_messages: No exception is shown; all six graph events report completed.
- timeline: Observed in the current local app on 2026-08-16; prior behavior is unknown.
- reproduction: Submit "I want something under 20 bucks" or "What is something I can buy under 20 bucks" through chat.

## Current Focus

- hypothesis: Confirmed — the query becomes the generic token "something," so arbitrary semantic neighbors are correctly rejected by lexical grounding.
- test: Exact-query trace, no-tool clarification tests, two-turn budget persistence test, and full regression suites.
- expecting: Vague turns ask a warm follow-up without retrieval; the narrowed response retains the original budget and searches normally.
- next_action: Resolved and verified.
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- timestamp: 2026-08-16T17:30:34Z
  observation: MCP log shows rag.search(query="something", price_max=20) returned five vector neighbors, followed by web.search(query="something").
- timestamp: 2026-08-16T17:35:00Z
  observation: semantic_query returns "something" for both screenshot phrases; the relevance gate rejects arbitrary titles lacking that term.
- timestamp: 2026-08-16T17:44:00Z
  observation: The fixed graph returns a clarification in four stages, marks retrieval skipped, makes no product claims, and returns zero products intentionally.

## Eliminated

- hypothesis: The new shopping-card renderer dropped valid products.
  reason: The graph returned products=[] before the UI rendered; card rendering was not involved.
- hypothesis: Catalog price filtering failed.
  reason: price_max=20.0 reached rag.search correctly; the failure was query specificity, not arithmetic filtering.

## Resolution

- root_cause: Budget-only language normalized to the generic semantic query "something." Vector search returned unrelated neighbors, the lexical grounding gate correctly rejected them, and generic web fallback produced no reliable budget-valid result.
- fix: Detect vague shopping queries before retrieval, ask one warm category/use-case question, preserve the pending budget across the next typed or spoken turn, and generate warmer evidence-only recommendations with title features and fit rationale.
- verification: 50 core/discovery tests and 38 app/voice tests pass; exact live-MCP graph trace skips retrieval and returns the clarification; Streamlit health endpoint returns ok.
- files_changed: graph/response_style.py, graph/fast_reply.py, graph/interactive.py, graph/nodes.py, graph/retriever.py, graph/answer.py, voice/livekit_agent.py, app/config.py, app/main.py, prompts/answerer.md, and regression tests.
