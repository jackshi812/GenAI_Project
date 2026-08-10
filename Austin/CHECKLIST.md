# Austin optional working guide

This is a lightweight memory aid. Austin may reorder, combine, or replace these
steps when another approach better satisfies the
[assignment](../Instructions.md), [plan](../.planning/phases/01-parallel-build/01-01-PLAN.md),
and stable interfaces in [`README.md`](README.md).

## Orient

- Read the assignment, Austin plan, locked context, and root `AGENTS.md`.
- Work only in `catalog/` and `mcp_server/`; coordinate root or cross-layer
  changes with Jack.
- Inspect the cleaned CSV and the Jack-owned shared files that are currently
  available. Missing shared files need not block work that does not use them.
- Keep credentials in an untracked local environment and keep generated index
  and log directories out of commits.

## Shape the catalog

- Normalize the cleaned CSV while preserving raw prices and nulls.
- Derive identifiers and brands conservatively; do not create private ratings.
- Build the Chroma collection in a way that can be rerun without duplicating
  products.
- Keep semantic product meaning separate from numeric/category/brand filters.
- Leave malformed-price products available to text retrieval.

Useful commands:

```bash
python -m catalog.normalize
python -m catalog.build_index
python -m catalog.smoke
```

## Coordinate the shared products

- Choose three useful canonical cases: budget, current price/availability, and
  private-versus-live comparison.
- Keep `semantic_query` about product meaning and place constraints in
  `filters`.
- Check expected IDs with the real retriever and update choices when the
  evidence suggests a better demo product.
- Make fixture keys unique under the shared first-eight-word normalization.
- Tell Ginger and Jack whenever a product title, expected ID, or boundary shape
  changes.

## Expose the tools

- Advertise only `rag.search` and `web.search`, with their JSON input schemas.
- Keep MCP stdout protocol-only and send diagnostics elsewhere.
- Normalize live and recorded Serper responses through the same path.
- Apply the retailer allowlist, cache repeated requests, space outbound calls,
  and log useful provenance without secrets.
- Use exact fixture matching; a missing key returns an honest empty result.

Useful commands:

```bash
env -u SERPER_API_KEY python -m mcp_server.smoke
python -m mcp_server.smoke
```

## Share and integrate

- Capture representative JSON from the real catalog and MCP code rather than
  writing examples by hand.
- Compare JSON types, `doc_id`, brand cleanup, private null ratings, tool names,
  and fixture keys with Ginger and Jack.
- Help Ginger at the MCP boundary while she owns the graph adapter.
- Help Jack diagnose end-to-end behavior while he coordinates application
  wiring and the combined flow.
- Give Jack factual implementation notes and known limitations for the final
  project documentation.

## Safety reminders

- Private prices come from the dataset; live prices and ratings come only from
  actual Serper live or recorded evidence.
- Never invent a rating, price, availability value, product, or citation.
- Never commit `.env`, credentials, generated Chroma data, or MCP logs.
- Pull before pushing, inspect what is staged, and avoid overwriting another
  contributor's work.
