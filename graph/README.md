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

## Blocked on Jack (as of Aug 11)

`contracts.py`, `fixtures.json`, `requirements.txt`, `.env.example` are not on
`main` yet. Everything here imports `contracts.py` per D-10, so runtime
verification beyond `test_deterministic` waits for those files. Two shapes to
confirm with Jack when they land (rename kwargs here if his fields differ):

- `Conflict(field, private_value, live_value, direction)`,
  `MatchInfo(score, verdict, reason)`, `Citation(kind, label, url)`,
  `StepEvent(node, tool, status, duration_ms, detail)`,
  `AssistantResult(transcript, intent, plan, answer_text, products, citations, steps)`.
- `fixtures.json` structure assumed by `graph/tools_stub.py`:
  `{"rag_results": {<eight-word key>: [RagResult...]}, "web_results": {<eight-word key>: [WebResult...]}}`
  (rag_results may also be a flat list applied to every query). Keys follow
  the shared D-08 rule: first eight whitespace-delimited words, lowercased.
