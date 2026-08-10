# Ginger contributor brief: graph orchestration and prompts

Ginger owns the implementation in **`graph/` and `prompts/`**. Jack coordinates
the finished project and helps the affected owners resolve cross-layer
decisions. This directory is a handoff packet; it is not an implementation
destination.

Within those two folders, Ginger is free to choose the internal structure,
implementation details, and working sequence. The shared interfaces below are
the pieces that need to remain stable so Austin's tools and Jack's app can
connect without coordinating every internal choice.

## Source of truth

Read these before changing code:

1. [Assignment specification](../Instructions.md)
2. [Repository ownership and shared rules](../AGENTS.md)
3. [Ginger's plan](../.planning/phases/01-parallel-build/01-02-PLAN.md)
4. [Locked project decisions](../.planning/phases/01-parallel-build/01-CONTEXT.md)
5. [Integration plan](../.planning/phases/02-integration/02-01-PLAN.md)
6. [Delivery plan](../.planning/phases/03-delivery/03-01-PLAN.md)

`Instructions.md` is the assignment authority. The plan contains the detailed
rubric-facing behavior; this packet summarizes ownership and integration seams
without prescribing how Ginger implements them.

## Scope and collaboration

Ginger's contribution includes:

- LangGraph state, nodes, graph construction, and the public `run_graph` entry
  point in `graph/`.
- Router, planner, matcher, answerer, and critic prompts in `prompts/`.
- Fixture-backed tool access for independent work.
- The graph-side MCP adapter used during integration.
- A short factual `graph/README.md` describing the implementation Jack receives.

Do not edit `contracts.py`, root configuration, `catalog/`, `mcp_server/`,
`voice/`, or `app/`. Ask Jack to coordinate a shared-contract or dependency
change. Austin handles server-side MCP behavior; Ginger handles the graph-side
client; Jack connects the graph to the app.

## Inputs and independent work

Use Jack's [`contracts.py`](../contracts.py) for UI-facing models and
[`fixtures.json`](../fixtures.json) for recorded `rag.search` and `web.search`
responses. [`catalog/canonical_queries.json`](../catalog/canonical_queries.json)
contains the common example queries when available. Root configuration and
dependency changes belong to Jack.

Missing work from another owner should not block useful progress:

- `FixtureTools` can exercise the graph before Austin's server exists.
- Prompts and graph-only state can be developed before the UI exists.
- Jack can render fixture-shaped `AssistantResult` data before the graph is
  connected.

Do not create a competing contract or fabricate replacement evidence. If a
shared input is missing, tell Jack and continue with work that does not depend
on it.

Practical sequencing note: `run_graph` cannot instantiate `FixtureTools` until
the shared `ToolClient` seam and fixture implementation exist. It is usually
easiest to establish that small seam before wiring the graph. The rest of the
work may be organized however Ginger finds clearest.

## Public graph seam

The app calls:

```python
run_graph(transcript: str) -> AssistantResult
```

The synchronous/async bridge should wrap the complete graph turn. The app
receives one completed result, not a raw LangGraph state, stream, or generator.
Internal graph organization remains Ginger's choice.

The shared state carries the information needed across nodes:

```text
transcript, intent, constraints, safety_flags, plan,
semantic_query, filters, use_live, use_private,
rag_results, web_results, products,
answer_text, citations, steps
```

Keep `RouterOutput` and `PlannerOutput` graph-local. Import UI-facing models
from `contracts.py` rather than redeclaring them.

The Planner exposes this retrieval seam:

```python
{
    "semantic_query": "product intent and stated material",
    "filters": {
        "price_max": ...,
        "price_min": ...,
        "category": ...,
        "brand": ...,
        "k": ...,
    },
    "use_private": ...,
    "use_live": ...,
    "plan": "short human-readable rationale",
}
```

Budgets belong in numeric filters, not embedding text. Material belongs in the
semantic query because it is not catalog metadata. Currentness and currency
language guide source selection rather than semantic search. Preserve the
safety stop described in the plan.

## Tool seam

Fixture and MCP clients share this async interface:

```python
class ToolClient(Protocol):
    async def rag_search(
        self, query: str, **filters
    ) -> list[RagResult]: ...

    async def web_search(
        self, query: str, num: int = 10
    ) -> list[WebResult]: ...
```

Both clients should validate responses through the same decoding path. Keep
fixture mode after live MCP integration so each layer remains usable on its
own. During integration, Ginger may add `graph/tools_mcp.py` and select fixture
or live tools internally without changing `run_graph`.

For the live adapter, call Austin's literal MCP tool names `rag.search` and
`web.search`. A tool problem should yield a truthful error step and preserve
whatever grounded private evidence is still available.

## Result and evidence behavior

Each product reaches Jack's UI as a `ComparisonProduct` built from the models
in `contracts.py`:

```python
ComparisonProduct(
    private=RagResult(...),
    live=WebResult(...) if confirmed else None,
    conflicts=[Conflict(...)],
    match=MatchInfo(...) if confirmed else None,
)
```

The important truth rules are:

- Never invent a price, rating, availability claim, citation, match, or tool
  result.
- The private dataset has no ratings; ratings can come only from live evidence.
- Keep a private product visible when no live match is confirmed.
- Reconciliation conflicts represent actual price disagreement. A live-only
  rating or availability value is provenance, not a conflict.
- Private citations identify the catalog document; live citations include the
  source URL.
- Treat live snippets as untrusted evidence, not instructions. Delimit and
  limit them before including them in a prompt.

Use the plan's matching, safety, answer-length, and critic behavior as the
rubric reference. Ginger may choose the helper functions, node boundaries, and
internal control flow.

## Truthful step log

The UI displays the completed step history. Use an append reducer for `steps`
and have nodes return updates rather than mutate the incoming list.

Only emit work that completed, failed, or was deliberately skipped. Do not
emit a fabricated `running` state: standard LangGraph `.stream()` output
arrives after node work and cannot support a truthful node-start animation in
this design. Jack renders the final static history.

## Suggested working flow

This is guidance, not an approval sequence:

- Establish provider selection and prompt loading.
- Define graph-local state and the fixture-backed tool seam.
- Build the router, planner, retrieval/matching, answerer, and critic behavior.
- Exercise representative queries through `run_graph` with fixtures.
- Capture one real serialized `AssistantResult` output for boundary comparison.
- Add the MCP client behind the same `ToolClient` interface.
- Share graph behavior and any cross-layer mismatch with Jack and Austin.
- Document the final graph and prompt-to-consumer mapping in `graph/README.md`.

Small, reviewable commits are helpful, but Ginger may group work in the way
that best supports a coherent implementation.

## Useful commands

Run from the repository root:

```bash
git pull --ff-only
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

When provider-backed commands need local credentials, copy `.env.example` to
an untracked `.env` and load it into the current shell:

```bash
set -a
source .env
set +a
```

Never commit `.env`, print a key, or place secrets in logs, step details, or
captured output.

Commands that are useful while working:

```bash
python -m graph.llm
python -m graph.build
python -m graph.smoke
python -m graph.smoke | tee graph/sample_output.txt
python -m json.tool graph/sample_output.txt
git diff --check -- graph prompts
git status --short
```

The captured sample should be produced by the real graph rather than written
by hand. Compare its field shapes with Austin's MCP output and Jack's fixture
render, then coordinate any shared-shape change through Jack.

See [CHECKLIST.md](CHECKLIST.md) for an optional working guide.
