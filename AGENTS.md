# Voice-to-Voice Product Discovery Assistant

Class final project. **Due August 20, 2026.** Three owners building in parallel.

`Instructions.md` is the assignment specification. It outranks everything in this file.

## Find your plan

| You | Your folders | Your plan |
|---|---|---|
| **Austin** | `catalog/`, `mcp_server/` | `.planning/phases/01-parallel-build/01-01-PLAN.md` |
| **Ginger** | `graph/`, `prompts/` | `.planning/phases/01-parallel-build/01-02-PLAN.md` |
| **Jack** | `voice/`, `app/`, repo root | `.planning/phases/01-parallel-build/01-03-PLAN.md` |

Read your plan end to end before writing code. Then read
`.planning/phases/01-parallel-build/01-CONTEXT.md` — sixteen locked decisions
(D-01 … D-16) that the plans cite by number rather than restate.

## Hard rules

- **Stay in your folders.** Only Jack writes `contracts.py`; Austin and Ginger import from it.
- **Nobody waits.** Ginger stubs both MCP tools from `fixtures.json`. Austin replays recorded Serper responses when there's no key. Jack renders the whole screen from fixtures. All three layers work before any real component exists — that is the design, not a workaround.
- **Never invent a rating or a price.** The dataset has no ratings at all. Ratings come only from live search results. Fabricating them defeats the grounding this assignment exists to teach and is trivially detectable.
- **Never commit `.env`. Never log an API key.**
- **Everyone commits to `main`.** Folders are disjoint so conflicts are rare. Pull before you push.

## What bites you in the data

`dataset/marketing_sample_for_amazon_com-ecommerce__20200101_20200131__10k_data.csv`, 10,002 rows:

- **Thirteen columns are 100% empty** — including `Brand Name`, `Ingredients`, `Sku`, `Asin`, `Product Description`. `sku` is derived from `Uniq Id`; `brand` is derived from the title and returns null when unsure.
- **There is no rating column and no rating-shaped value anywhere.**
- **385 rows have malformed prices** — ranges, duplicated values, raw CSS in the field.
- **Embeddings cannot do arithmetic.** "under twenty dollars" is a metadata filter, never a search term. This is the single most important retrieval fact in the project.

Full detail in `01-CONTEXT.md`.

## August 13 checkpoint

Each owner commits one **real captured output** — actual JSON your code produced, not a schema and not an example you wrote by hand. We compare the three shapes that day. It is the only scheduled sync, and it exists to catch the things type annotations miss: a price serialized as `"17.49"` instead of `17.49`, a brand with a trailing hyphen that will never match.

## Setup

Jack commits `requirements.txt`, `contracts.py`, `fixtures.json` and `.env.example` on day one. Until those land, install what you need as you go — nothing in anyone's opening tasks depends on them.

---

*`CLAUDE.md` and `AGENTS.md` are byte-identical. If you edit one, edit both.*
