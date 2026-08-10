# Voice-to-Voice Product Discovery Assistant

Class final project. Jack is the project owner and final integrator; three
technical owners build in parallel.

`Instructions.md` is the assignment specification. It outranks everything in this file.

## Find your plan

| You | Start here | Your implementation folders | Your authoritative plan |
|---|---|---|---|
| **Austin** | `Austin/README.md` | `catalog/`, `mcp_server/` | `.planning/phases/01-parallel-build/01-01-PLAN.md` |
| **Ginger** | `Ginger/README.md` | `graph/`, `prompts/` | `.planning/phases/01-parallel-build/01-02-PLAN.md` |
| **Jack** | `Jack/README.md` | `voice/`, `app/`, repo root | `.planning/phases/01-parallel-build/01-03-PLAN.md` |

The capitalized contributor folders are handoff packets, not implementation
destinations. Read your packet first, then write code only in the implementation
folders assigned above.

## Project accountability

- **Jack coordinates the finished project.** He maintains shared contracts,
  helps resolve cross-layer decisions, and brings together integration,
  documentation, presentation, and the final demo.
- Austin remains responsible for implementation in `catalog/` and
  `mcp_server/`. Ginger remains responsible for implementation in `graph/` and
  `prompts/`. Jack reviews their boundary outputs but does not take over their
  folders.
- During integration, Ginger implements the graph-side MCP adapter, Austin
  supports the server boundary, and Jack wires the app. Cross-layer tradeoffs
  should be discussed by the affected owners; Jack keeps the combined product
  coherent.
- After the parallel plans, follow
  `.planning/phases/02-integration/02-01-PLAN.md`, then
  `.planning/phases/03-delivery/03-01-PLAN.md`. Jack coordinates both phases.

Use your plan and
`.planning/phases/01-parallel-build/01-CONTEXT.md` as detailed references. The
context records sixteen shared decisions (D-01 … D-16) cited by the plans.

## Collaboration boundaries

- Work primarily in your assigned folders. Only Jack writes `contracts.py`;
  Austin and Ginger import from it. Discuss cross-folder changes first.
- Keep work independent where practical. Ginger can stub both MCP tools from
  `fixtures.json`, Austin can replay recorded Serper responses when there is no
  key, and Jack can render the screen from fixtures.
- **Never invent a rating or a price.** The dataset has no ratings at all. Ratings come only from live search results. Fabricating them defeats the grounding this assignment exists to teach and is trivially detectable.
- **Never commit `.env`. Never log an API key.**
- **Everyone commits to `main`.** Folders are disjoint so conflicts are rare. Pull before you push.

## What bites you in the data

`dataset/amazon_product_data_cleaned.csv`, 10,002 rows:

- The Kaggle original had **thirteen 100% empty columns** — including `Brand Name`, `Ingredients`, `Sku`, `Asin`, and `Product Description`. The working CSV drops them. `sku` is derived from `Uniq Id`; `brand` is derived from the title and returns null when unsure.
- **There is no rating column and no rating-shaped value anywhere.**
- **385 rows have malformed prices** — ranges, duplicated values, raw CSS in the field.
- **Embeddings cannot do arithmetic.** "under twenty dollars" is a metadata filter, never a search term. This is the single most important retrieval fact in the project.

Full detail in `01-CONTEXT.md`.

## Shared-output sync

Each owner shares one real captured output—actual JSON produced by the code, not
a hand-written schema or example. Compare the three shapes before integration
to catch issues type annotations miss, such as a price serialized as `"17.49"`
instead of `17.49` or brand punctuation that prevents matching.

## Setup

Before parallel work, Jack confirms
`dataset/amazon_product_data_cleaned.csv` is tracked on `main`; it is Austin's
starting input. Jack also helps the team obtain working Anthropic, OpenAI, and
Serper credentials through an approved private channel—never the repository,
committed files, logs, or group chat.

Jack shares `requirements.txt`, `contracts.py`, `fixtures.json`, and
`.env.example` early. Until those land, contributors may install what they need
locally and continue work that does not depend on the shared boundary.

---

*`CLAUDE.md` and `AGENTS.md` are byte-identical. If you edit one, edit both.*
