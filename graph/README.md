# graph/ — LangGraph orchestration (Ginger)

Four async nodes wired in sequence, one public entry point:

```
run_graph(transcript: str) -> AssistantResult          # graph/build.py

START -> router -> planner -> retriever -> answerer -> END
```

| Node | File | Does | Prompt |
|---|---|---|---|
| Router | `graph/nodes.py :: router_node` | transcript → task, numeric budget, category/brand/material, safety flags | `prompts/router.md` |
| Planner | `graph/nodes.py :: planner_node` | source selection (deterministic currency-keyword escalation first, LLM may add but never veto), rag filters, semantic query | `prompts/planner.md` |
| Retriever | `graph/retriever.py` | `rag.search`, per-product `web.search` (D-06), three-stage match (D-01), price reconciliation (D-02), no-match honesty (D-03) | `prompts/match_confirm.md` (stage C only) |
| Answerer/Critic | `graph/answer.py` | ≤30-word cited spoken answer; critic grounding check, one retry then degrade | `prompts/answerer.md`, `prompts/critic.md` |

Supporting modules: `graph/llm.py` (env-swappable provider + prompt loader),
`graph/state.py` (state schema, graph-internal models, `make_step`),
`graph/matching.py` (pure deterministic matching helpers, unit-testable with
no key), `graph/tools.py` (the async `ToolClient` seam + shared `_decode` +
eight-word fixture key), `graph/tools_stub.py` (fixture implementation; stays
as the recorded fallback after Phase 2 adds `graph/tools_mcp.py`).

## Verify

```bash
python -m graph.test_deterministic   # no key, no contracts.py needed
python -m graph.llm                  # proves env swappability + key works
python -m graph.build                # stub end-to-end, prints step log
python -m graph.smoke                # all three canonical queries
python -m graph.smoke | tee graph/sample_output.txt   # Aug 13 checkpoint
```

## Contract alignment (updated Aug 11, after Jack's push)

Verified against Jack's `contracts.py` (strict pydantic, `extra="forbid"`):
`MatchInfo.similarity`, `Conflict.note` (human-readable, no `direction`
field), `StepEvent.started_at` (recorded by `graph.state.timer`), and
`AssistantResult` without `intent` (intent stays graph-internal; it reaches
the step log via the router step's detail).

One divergence to raise with Jack at the Aug 13 checkpoint: `fixtures.json`
keys `web_results` by **full catalog title**, while D-08 specifies the
eight-word key. `graph/tools_stub.py` indexes both spellings of each key
(exact match after normalization, never fuzzy), so either convention works.
