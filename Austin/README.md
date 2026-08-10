# Austin contributor brief: catalog and MCP server

Austin owns the private product catalog, retrieval, and MCP server. Jack is the
project owner and final integrator. Austin has freedom to choose the internal
design, coding style, and working order as long as the public seams below stay
compatible with Ginger's graph and Jack's application.

Implementation belongs in `catalog/` and `mcp_server/`. This `Austin/` folder is
only a handoff packet. If a shared or root-level change would help, describe it
to Jack rather than editing another owner's files.

## Read first

Use these as the source of truth, in this order:

1. [`Instructions.md`](../Instructions.md) — assignment and grading rubric.
2. [Austin's plan](../.planning/phases/01-parallel-build/01-01-PLAN.md) — intended
   deliverables and assignment-specific details.
3. [Locked context](../.planning/phases/01-parallel-build/01-CONTEXT.md) — shared
   decisions D-01 through D-16.
4. [`AGENTS.md`](../AGENTS.md) — ownership and collaboration rules.
5. [Integration plan](../.planning/phases/02-integration/02-01-PLAN.md) and
   [delivery plan](../.planning/phases/03-delivery/03-01-PLAN.md) when handing
   work to the rest of the team.

If this brief conflicts with those files, follow `Instructions.md` and tell
Jack. The plan describes one workable implementation, not a restriction on
reasonable alternatives that preserve the rubric and interfaces.

## Your scope

Austin may edit:

- `catalog/`
- `mcp_server/`

Jack owns `contracts.py`, `requirements.txt`, `.env.example`, `.gitignore`, and
the repository root. Ginger owns `graph/` and `prompts/`. Jack also owns
`voice/` and `app/`.

Useful starting inputs:

| Input | How Austin uses it |
|---|---|
| `dataset/amazon_product_data_cleaned.csv` | Source for normalization and private retrieval. It contains 10,002 products. |
| `contracts.py` | Shared boundary models once Jack provides them; import rather than duplicate them. |
| `serper_fixtures.json` | Root-level mapping of exact fixture keys to raw Serper responses for no-key replay. |
| `catalog/canonical_queries.json` | Austin's shared product/query choices, consumed by Ginger and Jack. |

The working CSV already drops the thirteen empty source columns. Derive `sku`
from `Uniq Id`, use `About Product` for description/features, and derive a brand
only when the title makes it clear. The private dataset contains no ratings.

## Stable team interfaces

These are interoperability constraints. Everything behind them is Austin's
choice.

### Catalog search

Expose this public Python interface:

```python
search(
    query,
    price_max=None,
    price_min=None,
    category=None,
    brand=None,
    k=5,
) -> list[dict]
```

Send product meaning to semantic search. Apply price, category, and brand as
metadata filters; do not embed arithmetic such as "under twenty dollars."
Products with malformed prices should remain text-searchable even when they
cannot satisfy a numeric filter.

Private result objects expose these shared fields:

```text
sku, title, price, rating, brand, ingredients, doc_id
```

Additional UI/evidence fields are welcome if they do not change those fields.
`price_low` and `price_high`, when included, are JSON numbers or null rather
than numeric strings. Private `rating` and `ingredients` are null. Never infer
or fabricate them.

### Canonical queries

Choose three products that collectively support:

- a private-catalog budget question;
- a current-price or availability question; and
- a real private-versus-live price comparison for a comparable product variant.

Publish them in `catalog/canonical_queries.json` using the fields expected by
the plan: `id`, `transcript`, `semantic_query`, `filters`, `why`,
`expected_doc_ids`, `notes`, and `status`. Ginger and Jack use this file for
their fixtures and demo path, so tell them when product titles or expected IDs
change.

### MCP server

Run one stdio MCP server that advertises exactly these two tools:

```text
rag.search
web.search
```

Their public inputs are:

```text
rag.search: query (required); price_max, price_min, category, brand, k (optional)
web.search: query (required); num (optional)
```

`rag.search` returns the private result shape above. `web.search` returns:

```text
title, url, snippet, price, availability, rating
```

Use only real live or recorded Serper shopping responses for live fields.
Filter live URLs to the retailer allowlist before returning them. Reconciliation
does not belong in the MCP server; Ginger combines private and live evidence in
the graph.

Keep stdout exclusively for MCP protocol traffic. Operational information may
go to stderr or `mcp_server/logs/mcp.jsonl`. Logs should identify the tool,
direction, timing/result count, and source URLs where relevant without exposing
credentials.

### Exact fixture seam

All three owners use the same key rule:

```python
fixture_key = " ".join(product_title.split()[:8]).lower()
```

This means: take the first eight whitespace-delimited title words, lowercase
them, and collapse whitespace. Apply the same normalization to stored keys and
incoming queries, then require an exact match. A fixture miss returns an empty
list and is logged. Do not use fuzzy fallback, because it can attach evidence
from the wrong product.

When `SERPER_API_KEY` is absent, replay the matching raw response from root
`serper_fixtures.json` through the same normalization code used by live Serper
shopping results.

## Suggested implementation shape

Adapt this sequence freely. It is offered to reduce coordination surprises,
not as a prescribed workflow.

1. Normalize the CSV into `catalog/products.parquet`, retaining the original
   price text and a parsed numeric range when possible.
2. Choose provisional canonical products early so Ginger and Jack can build
   against realistic names and shapes.
3. Build the persistent Chroma collection and hybrid `search()` function.
4. Exercise the canonical queries against real retrieval, then refine the
   product choices and expected IDs if needed.
5. Expose retrieval through `rag.search` in the stdio MCP server.
6. Add Serper shopping, allowlist filtering, caching, rate limiting, logging,
   and exact fixture replay for `web.search`.
7. Capture representative JSON generated by the real catalog and MCP code for
   the team to compare with graph and UI outputs.

The plan suggests these files, but Austin may organize helpers differently
inside the two owned folders:

```text
catalog/normalize.py
catalog/products.parquet
catalog/build_index.py
catalog/search.py
catalog/smoke.py
catalog/canonical_queries.json
catalog/sample_output.txt
mcp_server/server.py
mcp_server/web_search.py
mcp_server/smoke.py
mcp_server/sample_output.txt
```

## Useful local commands

These are convenient checks, not a mandatory ceremony:

```bash
python -m catalog.normalize
python -m catalog.build_index
python -m catalog.smoke
env -u SERPER_API_KEY python -m mcp_server.smoke
python -m mcp_server.smoke
python -m json.tool catalog/canonical_queries.json
```

To load a private local `.env` into a fresh shell before a live run:

```bash
set -a
source .env
set +a
```

Keep `catalog/chroma/`, `mcp_server/logs/`, `.env`, API keys, and machine-local
artifacts out of commits. If an ignore rule is missing, ask Jack to update the
root `.gitignore`.

## Truth and failure behavior

- Never invent a product, price, rating, availability value, or source URL.
- Preserve the raw catalog price when parsing fails; do not silently convert a
  malformed value to zero.
- A missing fixture, live-search failure, or rate limit may produce no live
  evidence. Keep that state explicit rather than replacing it with a guess.
- A product without a live match remains a valid private result. Ginger and
  Jack handle the downstream empty state.
- Never commit `.env`, log an API key, or put a key in a command argument.

## Team handoff

Share real outputs rather than hand-written schema examples:

- `catalog/canonical_queries.json`
- `catalog/sample_output.txt`
- `mcp_server/sample_output.txt`
- the two MCP discovery schemas
- any known limitation or changed boundary shape

When comparing outputs with Ginger and Jack, focus on details that type hints
often miss: JSON number versus string, exact `doc_id`, punctuation in derived
brands, null private ratings, exact tool names, and fixture-key collisions.

During integration, Ginger owns the graph-side MCP adapter and Jack coordinates
the application wiring and combined flow. Austin supports the catalog/server
boundary and fixes defects within `catalog/` or `mcp_server/`. Austin can
propose cross-layer changes; Jack coordinates any edit outside Austin's scope.

For final documentation, give Jack concise factual notes about normalization,
malformed prices, retrieval filters, MCP schemas, Serper provenance, fixture
replay, caching/rate limiting, logging, and known limitations. Jack combines
those notes into the project-level documentation and demo.

Use [`CHECKLIST.md`](CHECKLIST.md) as an optional working guide.
