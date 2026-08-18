---
status: resolved
trigger: "I don't know help me decide returns no grounded match; remove two results captions and show more than three products"
created: 2026-08-16
updated: 2026-08-16
diagnose_only: false
---

# Delegated choice produces no results

## Symptoms

- expected_behavior: When the shopper delegates the choice, the configured LLM selects a sensible grounded search direction using prior constraints; the UI omits redundant source/advisory captions and shows more than three products.
- actual_behavior: "I don't know help me decide" becomes a literal product query and returns no grounded match. The right panel shows two unwanted captions and caps results at three.
- error_messages: No exception is shown.
- timeline: Observed in the current local app on 2026-08-16.
- reproduction: Ask for broad help or reject results, then submit "I don't know help me decide."

## Current Focus

- hypothesis: Confirmed — delegated-choice language had no dedicated intent, so generic conversational words passed through semantic retrieval; the three-product limit was hardcoded at retrieval, voice-preview, grid, and table layers.
- test: Model/fallback decision, exact-query routing, six-result retrieval, Streamlit rendering, full graph/MCP, and voice regression suites.
- expecting: A delegated turn chooses a concrete search direction, retrieves only grounded products, and displays up to six without the two requested captions.
- next_action: Resolved and verified.
- reasoning_checkpoint:
- tdd_checkpoint:

## Evidence

- timestamp: 2026-08-16T18:20:00Z
  observation: Screenshot shows delegated-choice language reaching the generic no-match response.
- timestamp: 2026-08-16T18:24:00Z
  observation: semantic_query("I don't know help me decide") produced "don't know help decide", which is not a product phrase and was sent to retrieval before the fix.
- timestamp: 2026-08-16T18:27:00Z
  observation: Catalog probes confirm six grounded results for every constrained decision option used by the fallback, including puzzle, game, storage, and basketball directions.
- timestamp: 2026-08-16T18:31:00Z
  observation: The fixed graph test has the LLM select storage, forwards query="storage", category="Home & Kitchen", price_max=20, k=6, makes no web call, and returns six products.

## Eliminated

- hypothesis: The catalog has too few products to return more than three.
  reason: Direct catalog searches returned six matching rows; downstream caps discarded the extras.
- hypothesis: A second product-generation LLM is required.
  reason: The existing configured LLM only needs to select a constrained direction or grounded candidate; normal RAG retrieval and evidence-only response composition remain authoritative.

## Resolution

- root_cause: "I don't know help me decide" normalized to the meaningless search phrase "don't know help decide" because delegation was not represented as an intent. Separately, result limits of three existed in the retriever, voice preview, card grid, and comparison table. The two captions were emitted unconditionally for catalog-only results.
- fix: Added an LLM-assisted delegated-choice intent using the existing configured model. It can choose only a catalog-backed search option or an already grounded candidate; product facts still come exclusively from RAG/web evidence, with a verified fallback if the model is unavailable. Prior budgets and rejected categories flow through typed and voice dialogue context. Standardized retrieval/rendering to six products (three columns by two rows) and suppressed the requested catalog-only/advisory captions.
- verification: 61 core graph/MCP tests and 43 app/voice tests pass (104 total); the exact Streamlit three-turn regression retains the $20 budget, excludes the rejected category, renders six cards, and asserts both captions are absent. Streamlit health endpoint returns ok.
- files_changed: graph/decision.py, graph/response_style.py, graph/fast_reply.py, graph/interactive.py, graph/nodes.py, graph/retriever.py, graph/answer.py, graph/state.py, app/main.py, app/product_grid.py, voice/livekit_agent.py, mcp_server/server.py, prompts/decision.md, prompts/planner.md, prompts/answerer.md, and regression tests.
