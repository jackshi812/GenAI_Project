# Voice-to-Voice Product Discovery Assistant

Class final project. Jack is the project owner and sole technical maintainer.
Austin and Ginger completed their assigned work and formally handed their
implementation areas to Jack.

`Instructions.md` is the assignment specification. It outranks everything in this file.

## Ownership and historical plans

| Contributor | Handoff packet | Work completed | Historical plan |
|---|---|---|---|
| **Austin** | `Austin/README.md` | `catalog/`, `mcp_server/` | `.planning/phases/01-parallel-build/01-01-PLAN.md` |
| **Ginger** | `Ginger/README.md` | `graph/`, `prompts/` | `.planning/phases/01-parallel-build/01-02-PLAN.md` |
| **Jack** | `Jack/README.md` | `voice/`, `app/`, repo root | `.planning/phases/01-parallel-build/01-03-PLAN.md` |

The contributor folders and Phase 1 plans preserve build history and design
context; they no longer restrict implementation ownership. **Jack owns and may
change the entire repository**, including `catalog/`, `mcp_server/`, `graph/`,
`prompts/`, `voice/`, `app/`, shared contracts, planning artifacts, and repo-root
configuration.

## Project accountability

- **Jack owns the finished project end to end.** He maintains every layer,
  shared contract, integration point, test, document, presentation, and demo.
- Austin's and Ginger's contributions remain part of the project history, but
  they have no active folder restrictions or required approval gates after the
  handoff.
- Jack resolves cross-layer tradeoffs and may refactor across folders while
  preserving the architectural and grounding rules in this file.
- After the parallel plans, follow
  `.planning/phases/02-integration/02-01-PLAN.md`, then
  `.planning/phases/03-delivery/03-01-PLAN.md`. Jack coordinates both phases.

Use your plan and
`.planning/phases/01-parallel-build/01-CONTEXT.md` as detailed references. The
context records sixteen shared decisions (D-01 … D-16) cited by the plans.

## Collaboration boundaries

- Jack may work in every implementation folder. `contracts.py` remains the
  single source of truth for shared public models.
- Preserve clean layer boundaries: the app renders graph results, the graph
  owns orchestration and reconciliation, and the MCP server exposes the two
  specified evidence tools.
- **Never invent a rating or a price.** The dataset has no ratings at all. Ratings come only from live search results. Fabricating them defeats the grounding this assignment exists to teach and is trivially detectable.
- **Never commit `.env`. Never log an API key.**
- Jack commits integrated work to `main` and keeps changes scoped and tested.

## What bites you in the data

`dataset/amazon_product_data_cleaned.csv`, 10,002 rows:

- The Kaggle original had **thirteen 100% empty columns** — including `Brand Name`, `Ingredients`, `Sku`, `Asin`, and `Product Description`. The working CSV drops them. `sku` is derived from `Uniq Id`; `brand` is derived from the title and returns null when unsure.
- **There is no rating column and no rating-shaped value anywhere.**
- **385 rows have malformed prices** — ranges, duplicated values, raw CSS in the field.
- **Embeddings cannot do arithmetic.** "under twenty dollars" is a metadata filter, never a search term. This is the single most important retrieval fact in the project.

Full detail in `01-CONTEXT.md`.

## Shared-output sync

The Phase 1 owners shared real captured outputs—actual JSON produced by the
code, not hand-written schemas. Keep comparing boundary shapes during
integration to catch issues type annotations miss, such as a price serialized
as `"17.49"` instead of `17.49` or brand punctuation that prevents matching.

## Setup

`dataset/amazon_product_data_cleaned.csv` must remain tracked on `main`. Keep
Anthropic, OpenAI, and Serper credentials in approved private configuration—never
the repository, committed files, logs, or chat. Shared setup lives in
`requirements.txt`, `contracts.py`, `fixtures.json`, and `.env.example`.

---

*`CLAUDE.md` and `AGENTS.md` are byte-identical. If you edit one, edit both.*
