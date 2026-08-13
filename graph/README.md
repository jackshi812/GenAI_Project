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
eight-word fixture key), `graph/tools_stub.py` (fixture implementation, kept
as the explicit recorded fallback), `graph/tools_mcp.py` (Phase 2 live
client: one `python -m mcp_server.server` subprocess and one initialized
`ClientSession` per graph turn, shared by `rag.search` and every
`web.search` call).

Tool selection is env-driven and does not change `run_graph`'s signature:
`TOOL_MODE=live` (default) uses `MCPTools`; `TOOL_MODE=fixture` replays
recorded data. A failed tool call raises `RuntimeError` at the client
boundary; the Retriever converts it into an empty result plus a truthful
`status: error` step — private evidence is preserved and nothing is
invented.

## Verify

```bash
python -m graph.test_deterministic            # pure logic, nothing installed
python -m unittest discover -s graph -p 'test_*.py'   # all unit tests
python -m graph.llm                           # env swappability + key check
TOOL_MODE=fixture python -m graph.smoke       # recorded end-to-end
TOOL_MODE=live python -m graph.smoke          # real MCP server end-to-end
```

Live-mode `rag.search` requires Austin's Chroma index
(`python -m catalog.build_index`); without it the step degrades to a truthful
`error` and the turn still completes.

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
