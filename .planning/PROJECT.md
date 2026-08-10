# Voice-to-Voice Product Discovery Assistant

## What This Is

A hands-free shopping assistant. The user speaks a request — *"find me a 500 piece
puzzle under twenty dollars"* — and a LangGraph multi-agent pipeline classifies the
intent, plans which sources to consult, retrieves grounded evidence from a private
Amazon product catalog via vector search, checks live web prices when the question
warrants it, and answers out loud with citations displayed on screen.

Built as a class final project by a three-person team, due August 20, 2026. The
assignment specification lives in `Instructions.md` at the repo root and is the
authority on requirements; its grading rubric drives prioritization throughout.

## Core Value

A spoken question returns a grounded, cited recommendation that visibly reconciles
stale private catalog data against live web data. If everything else fails, that
reconciliation — private evidence and live evidence side by side, disagreements
surfaced rather than hidden — must work.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] User speaks a product request and receives a spoken answer without touching a keyboard
- [ ] Requests are transcribed accurately enough to drive downstream retrieval
- [ ] A LangGraph pipeline routes intent, plans sources, retrieves, and answers as distinct cooperative nodes
- [ ] Budget, category and brand constraints are extracted from speech and applied as structured filters
- [ ] Private catalog retrieval combines vector similarity with metadata filtering
- [ ] A single MCP server exposes exactly two tools, `rag.search` and `web.search`, with working discovery and JSON schemas
- [ ] Live web results are fetched, cached with a TTL, rate-limited, and logged per request
- [ ] Private and live results are reconciled, with disagreements surfaced as explicit conflicts
- [ ] Every claim in the spoken answer traces to a private document ID or a live URL
- [ ] The screen shows a top-three comparison table, the agent step log, and data lineage
- [ ] The answer is synthesized to speech and playable, capped at roughly fifteen seconds
- [ ] The LLM provider is swappable through environment configuration
- [ ] Prompts are disclosed with an explicit mapping to their LangGraph nodes and tools

### Out of Scope

- Streaming ASR and TTS — the spec explicitly permits fragment-based processing and encourages it for simplicity; streaming buys no rubric points
- Reranking layer — marked optional in the spec, and retrieval quality is adequate without it at this corpus size
- `reviews.parquet` — marked optional, and the dataset carries no review data to populate it
- Multilingual accent handling — nothing in the rubric rewards it
- Containerization, CI, and a real test suite — ten-day timeline, and none of it is graded
- Authentication, persistence, multi-user support — single-session demo application
- Fabricated ratings or prices — the dataset lacks ratings entirely; inventing them would defeat the grounding the assignment exists to teach

## Context

**The dataset does not match what the assignment assumes.** The mandated corpus is
the PromptCloud *Amazon Product Dataset 2020* from Kaggle, and inspection of all
10,002 rows found that thirteen of its twenty-eight columns are entirely empty —
including `Brand Name`, `Ingredients`, `Sku` and `Asin`. There is no rating column,
and no rating-shaped value anywhere in any other field. A second copy of the file
sourced from HuggingFace turned out to be the identical row set with the empty
columns dropped, so it adds nothing.

The spec suggests slicing to Household Cleaning, but that category effectively does
not exist here: a keyword sweep returns 55 rows and nearly all are false positives
(`Bleach Kisuke Hat` is anime merchandise, `Spring Clean Up` is a jigsaw puzzle).
Actual composition is 6,662 Toys & Games, 708 Home & Kitchen, 630 Clothing, 540
Sports & Outdoors, and a long tail. Prices are dirty in 385 rows — ranges,
duplicated values, and in some cases raw CSS leaking into the field.

This shapes the architecture rather than blocking it. The private catalog carries
rich descriptions and specifications but a 2020 price snapshot and no ratings; live
web search carries current price, availability and rating but little detail. Neither
source can answer a question alone, which makes reconciliation genuinely necessary
instead of a contrived exercise — and reconciliation is a graded criterion.

**Team structure drives the phase design.** Three people working ten days in
parallel, with almost no tolerance for one person blocking another. The assignment
happens to define two of the three internal interfaces verbatim, which makes near-
zero-handoff parallel work feasible from day one.

## Constraints

- **Timeline**: Ten days, August 10 to August 20, 2026 — hard external deadline, no extension
- **Team**: Three people working simultaneously — work must partition into independent tracks, and the seams must be cheap
- **Tech stack**: LangGraph is mandatory for orchestration (spec line 15) — no substitutions
- **Tech stack**: Exactly one MCP server exposing exactly two named tools (spec line 73) — not one, not three
- **Tech stack**: LLM must be swappable via environment variable or config (spec line 149)
- **Data**: The Amazon Product Dataset 2020 is mandated as the primary private corpus (spec line 173) — swapping it risks the grade, so its gaps must be designed around rather than replaced
- **Data**: No ratings, brands, ingredients or SKUs exist in the source — derived or externally sourced values must be honest about their provenance
- **Grading**: A published rubric allocates all 100 points — scope decisions defer to it
- **Safety**: Domain allowlist, respect `robots.txt` and terms of service, never log secrets (spec line 236)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep the mandated dataset despite its gaps | Spec names it explicitly; swapping risks the grade and costs a day of rework that would block the whole team | — Pending |
| Index all ~10,000 rows rather than one category slice | The suggested Household Cleaning slice does not exist in this data; the spec says "such as", making it an example rather than a mandate | — Pending |
| Source ratings from `web.search`, never fabricate | The catalog has none; inventing them would defeat the grounding the assignment teaches and is trivially detectable | — Pending |
| Serper for web search, shopping endpoint | Returns structured price *and* rating, which patches the catalog's missing-ratings gap; snippet-only APIs would require regexing prices out of prose | — Pending |
| Claude for agents, swappable via env | Strongest tool-calling for the router and planner nodes; swappability is a spec requirement regardless of choice | — Pending |
| OpenAI Whisper API and OpenAI TTS | One key already held covers both; network is already a hard dependency via `web.search`, so local ASR buys no resilience | — Pending |
| Streamlit over React | React costs an entire track the ten-day timeline cannot absorb; UI is worth 10 points and Streamlit earns them | — Pending |
| Chroma over FAISS | Metadata filtering is a spec requirement and Chroma expresses it more directly | — Pending |
| MCP over stdio rather than HTTP/SSE | Spec permits either; stdio removes a server process from the demo path | — Pending |
| Jack owns both pipeline ends plus integration | Owner prefers multiple parts and cares most about the user-facing design; places the graded-visible surface with the person who wants it | — Pending |
| Fragment-based ASR and TTS | Spec calls it acceptable and encouraged; streaming adds risk for zero rubric gain | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-08-10 after initialization*
