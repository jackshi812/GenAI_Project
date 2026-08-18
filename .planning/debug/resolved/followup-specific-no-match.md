---
status: resolved
trigger: "Specific follow-ups such as medium or large and bedding requests end in the same fixed no-grounded-match response; 'just give me anything' also repeats it."
created: 2026-08-16
updated: 2026-08-16
diagnose_only: false
---

# Specific and delegated follow-ups lose shopping intent

## Symptoms

- expected_behavior: Preserve the active product and budget, accept alternative sizes, normalize a spoken bedding request, and let an explicit delegation choose a grounded option.
- actual_behavior: The assistant returns the same no-grounded-match template for specific requests and for “just give me anything.”
- error_messages: No exception; semantic failure shown in the chat.
- timeline: Reproduced in the current conversational voice build.
- reproduction: Ask for men’s sportswear under $20 and answer “medium or large”; separately ask for a quilt, comforter set, or pillow, then say “can you just give me anything?”

## Current Focus

- hypothesis: Confirmed. Multiple independent fallbacks compounded into the same visible apology.
- test: Exact screenshot transcripts through parser, mocked graph, real catalog/MCP retrieval, and bounded response-model timing.
- expecting: New products reset stale context; preference answers trigger retrieval; six grounded products survive sparse facet evidence; natural response finishes before timeout.
- next_action: Resolved and verified.
- reasoning_checkpoint: The requested preference is a filter/ranking goal, never evidence that a listing has that attribute.
- tdd_checkpoint: green; four initial regressions failed before the fix and now pass.

## Evidence

- “Medium or large?” parsed both sizes correctly, but the old retriever searched the literal combined query and then discarded every result lacking both title words.
- The bedding utterance became `use on my bed quilt or comforter set or pillow`; the corrected profile is `bedding`, routed to `Home & Kitchen`.
- “Can you just give me give me anything?” did not match delegation patterns and incorrectly invoked a canned unrelated direction.
- A bare `iPhone 12` was classified as a short follow-up, retaining men’s sportswear and its $20 budget. It now starts a clean search.
- The interactive retriever intentionally truncated catalog results to one whenever live search was planned; a real MCP bedding run now returns six catalog products.
- The natural-answer model measured about 7.1 seconds at its previous default effort while the code cancelled it at 6 seconds. Low reasoning measured about 3.7 seconds on the same synthetic grounded task.

## Eliminated

- Catalog data absence was not the general cause: the local catalog contains many bedding/comforter products.
- A second response model is not required: the existing configured model can perform bounded preference interpretation and final wording.
- UI rendering was not generating the apology; the graph returned an empty product list before rendering.

## Resolution

- root_cause: Over-broad follow-up classification leaked stale context; facet terms were used as strict retrieval words and hard filters; sparse evidence collapsed valid result sets; delegation and spoken product-family wording were under-normalized; natural answers timed out into templates.
- fix: Added new-product/reset detection, generic preference clearing, domain-aware feature answers, bedding normalization, active-request delegation, broad catalog recall with post-retrieval facet ranking, honest closest-result fallback, twelve-candidate live discovery, six-card preservation, low reasoning effort, an 8-second response ceiling, and deterministic unsupported-preference claim rejection.
- verification: 104 Python tests pass; 8 frontend tests pass; real MCP bedding request returns six products; real Serper iPhone search returns six products; local services restarted and `http://localhost:8501` returns HTTP 200.
- files_changed: `.env.example`, `graph/answer.py`, `graph/fast_reply.py`, `graph/interactive.py`, `graph/llm.py`, `graph/preferences.py`, `graph/relevance.py`, `graph/response_style.py`, `graph/retriever.py`, `voice/livekit_agent.py`, and regression tests.
