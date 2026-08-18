# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## top-recommendation-mismatch — Assistant recommendation did not match the first product card
- **Date:** 2026-08-17
- **Error patterns:** WANGE Taipei 101, $104.44, first displayed card, different product, spoken text, match rationale, no runtime exception
- **Root cause:** The deterministic router/fast path had only upper-budget parsing and hard-coded budget_min=None, so range numbers polluted semantic retrieval instead of becoming numeric metadata filters. Independently, recommendation identity was duplicated: the LLM could select any grounded product, while the app rendered retriever order and the public result carried no canonical top metadata/reason.
- **Fix:** Added numeric/spoken range parsing and semantic-clause removal; forwarded both existing numeric filter keys; added graph-owned TopRecommendation metadata with stable doc_id/URL identity and grounded reason; constrained prose to products[0], reordered explicit selections, rendered one first-card badge/reason, and preserved both bounds through app/voice follow-ups and preliminary web results.
- **Files changed:** contracts.py, graph/state.py, graph/fast_reply.py, graph/nodes.py, graph/interactive.py, graph/answer.py, graph/recommendation.py, graph/build.py, app/product_grid.py, app/main.py, voice/livekit_agent.py, graph/test_fast_reply.py, graph/test_answer.py, graph/test_interactive.py, app/test_product_grid.py, app/test_main.py, voice/test_livekit_agent.py
---

