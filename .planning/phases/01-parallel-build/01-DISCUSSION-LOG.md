# Phase 1: Parallel Build - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-10
**Phase:** 1-Parallel Build
**Areas discussed:** Reconciliation & conflicts, Live search behavior, Contract & team seams, Demo surface & wow factor

---

## Reconciliation & Conflicts

### Matching rule

| Option | Description | Selected |
|--------|-------------|----------|
| Fuzzy title similarity | Token overlap above a threshold, single best match. Deterministic, fast, score displayable. | |
| LLM-judged match | Catalog title plus top three live titles sent to the LLM with a confidence value. Robust to phrasing, nondeterministic in demo. | |
| Similarity shortlist + LLM confirm | Token overlap narrows to two or three candidates, then the LLM confirms. Most accurate, most code, spans two owners. | ✓ |

**User's choice:** Similarity shortlist + LLM confirm
**Notes:** Chose the most capable option despite it spanning both Austin's and Ginger's work. Ownership was resolved in a later question — it all landed in Ginger's node.

### Conflict definition

| Option | Description | Selected |
|--------|-------------|----------|
| Per-field provenance | Every field shows its source; disagreements highlight. Serves spec line 143 directly. | ✓ |
| Price + availability + stale flag | Three badge types. Simpler, says nothing about individual field origins. | |
| Price delta only | One badge above a percentage threshold. Cheapest, underuses the project's strongest asset. | |

**User's choice:** Per-field provenance
**Notes:** Flagged at the time that this changes the contract — it needs a source tag per field, not just a conflicts list. That consequence was carried into the contract discussion.

### Unmatched products

| Option | Description | Selected |
|--------|-------------|----------|
| Show it, labeled "no live match" | Private data only with an explicit empty state. Honest; delisted listings are a real finding. | ✓ |
| Rank it below matched products | Still shown but sorted lower. Better-looking demo, quietly hides match failure rate. | |
| Drop and backfill | Skip and pull the next matching candidate. Cleanest screen, discards valid private results. | |

**User's choice:** Show it, labeled "no live match"

### Ownership

| Option | Description | Selected |
|--------|-------------|----------|
| Entirely Ginger's Retriever node | Spec line 36 assigns reconciliation to the Retriever; MCP is capped at two tools. No new seam. | ✓ |
| Shared reconcile/ module | Ginger writes it, Austin imports for sanity checks. Earlier feedback, one more shared file. | |
| Split: Austin scores, Ginger confirms | Spreads work but creates a real dependency between owners. | |

**User's choice:** Entirely Ginger's Retriever node

---

## Live Search Behavior

### Serper endpoint

| Option | Description | Selected |
|--------|-------------|----------|
| Shopping endpoint | Structured price, rating, seller, product link. The only source of ratings in the system. | ✓ |
| Web search endpoint | Organic results; price and rating would need regexing out of prose. Loses ratings. | |
| Both endpoints | Best coverage, doubles calls and normalization work. | |

**User's choice:** Shopping endpoint

### Query construction

| Option | Description | Selected |
|--------|-------------|----------|
| Per-product, from matched catalog title | One query per top candidate, ~3 per turn. Makes per-field provenance meaningful. Justifies the graded cache and rate limiter. | ✓ |
| One category-level query | One call per turn. Reconciliation degrades to vague market-price comparison. | |
| Both | Richest, most calls, most normalization. | |

**User's choice:** Per-product, from the matched catalog title

### Domain allowlist

| Option | Description | Selected |
|--------|-------------|----------|
| Retailer allowlist | Short explicit list; anything outside is dropped. Literal reading of spec line 236. | ✓ |
| Blocklist | Wider coverage, weaker safety story. | |
| No filter, document Serper as vetted | Least code, contradicts a written spec line. | |

**User's choice:** Retailer allowlist

### Working without a key

| Option | Description | Selected |
|--------|-------------|----------|
| Recorded fixture responses | Real Serper JSON captured once and replayed when the key is unset. Unblocks Austin, real shapes, doubles as demo offline fallback. | ✓ |
| Hand-written fake responses | Fastest start, risks the exact bug class the Aug 13 checkpoint exists to catch. | |
| Wait for the key | No throwaway code, puts a 15-point component behind an errand. | |

**User's choice:** Recorded fixture responses
**Notes:** Creates one dependency — a key is needed once, on day one, to record the fixtures. Captured as a task rather than a standing blocker.

---

## Contract & Team Seams

### Graph-to-interface result shape

| Option | Description | Selected |
|--------|-------------|----------|
| Side-by-side sub-objects + conflicts[] | product.private{} and product.live{} plus precomputed conflicts. Mirrors the comparison table; UI stays dumb. | ✓ |
| Per-field envelope | Every field becomes {value, source, ref}. Maximum explicitness, verbose, UI unwraps everything. | |
| Flat product + provenance map | Clean objects, separate provenance map. UI must join on every render. | |

**User's choice:** Side-by-side sub-objects + conflicts[]

### Contract form

| Option | Description | Selected |
|--------|-------------|----------|
| contracts.py (pydantic) + fixtures.json | Single source of truth, runtime validation catches string-vs-number price bugs immediately. | ✓ |
| JSON Schema files | Language-neutral, doubles as MCP tool schemas. More ceremony, no autocomplete. | |
| Fixtures only, no code | Zero setup, nothing enforces the shape, drift surfaces at integration. | |

**User's choice:** contracts.py (pydantic) + fixtures.json

### Git mechanics

| Option | Description | Selected |
|--------|-------------|----------|
| One repo, direct to main | Disjoint folders make conflicts near-zero. Continuous visibility, least ceremony. | ✓ |
| Branch per person | Standard isolation, costs merge rounds and delays shape verification. | |
| Separate repos | Maximum isolation, turns integration into packaging plus wiring. | |

**User's choice:** One repo, direct to main

### Brief format

| Option | Description | Selected |
|--------|-------------|----------|
| Per-folder CLAUDE.md + AGENTS.md | Auto-loaded by Claude Code and by Codex/Cursor respectively. Zero setup, no GSD install. Two copies to sync. | ✓ |
| Single root TEAM.md | Easiest to keep consistent, but no agent auto-loads it. | |
| GSD PLAN.md files directly | Best fidelity, adds an install and a new tool on day one. | |

**User's choice:** Per-folder CLAUDE.md + AGENTS.md
**Notes:** Chosen without confirming which agent each teammate uses — the format works for all of them, which removes the need to ask.

---

## Demo Surface & Wow Factor

### Layout

| Option | Description | Selected |
|--------|-------------|----------|
| Two column — conversation left, evidence right | Both halves visible at once; evidence appears while the presenter talks. | ✓ |
| Single column, top to bottom | Simplest, but the reconciliation moment sits below the fold. | |
| Answer first, evidence in tabs | Cleanest, but hides graded material behind clicks during a timed demo. | |

**User's choice:** Two column — conversation left, evidence right

### Interface feature scope

| Option | Description | Selected |
|--------|-------------|----------|
| Per-field source badges | Core value made visible; implied by the provenance decision. | ✓ |
| Product images in the table | Dataset has image URLs; near-zero work, large polish payoff. | ✓ |
| Match confidence per product | Falls out of the shortlist-plus-confirm decision; mostly display work. | ✓ |
| Live agent graph | Nodes light up as they execute. Flashiest and most expensive — needs streamed node events. | ✓ |

**User's choice:** Everything — all four
**Notes:** The question was initially declined so the user could ask what Phase 1 actually is. After the explanation ("everyone builds their own layer at the same time, against fakes"), the answer was "everything". The live agent graph's cost was restated at the time: it constrains how GRAPH-06 records step data, since an after-the-fact log will not drive it.

### Voice flow

| Option | Description | Selected |
|--------|-------------|----------|
| One click, then fully hands-free | Record, stop, then transcribe, run and speak automatically. Play button remains for replay. | ✓ |
| Confirm transcript before running | Catches ASR errors before burning a run, costs the hands-free claim. | |
| Auto-run but require Play | Avoids autoplay-policy failure, breaks the voice-to-voice loop. | |

**User's choice:** One click, then fully hands-free
**Notes:** Browser autoplay policy blocking first playback is a known accepted risk.

### Canonical queries

| Option | Description | Selected |
|--------|-------------|----------|
| Three fixed queries, one per path | Budget, currency escalation, and conflict. Exercises every graded path; becomes the demo script. | ✓ |
| One golden query | Fastest to a vertical slice, leaves escalation and conflict paths untested until integration week. | |
| No fixed queries | Maximum freedom, three layers tuned to different products. | |

**User's choice:** Three fixed queries, one per path
**Notes:** Exact product selection requires inspecting the data — deferred to planning as a task.

---

## Claude's Discretion

- Dependency management: one pinned `requirements.txt` with a virtual environment at the repository root.
- Embedding model selection, similarity metric, and threshold values.
- Internal structure of the step log, subject to the live-agent-graph constraint.

## Deferred Ideas

None — discussion stayed within phase scope.

## Withdrawn Mid-Discussion

- A mid-turn message proposed adding an LLM confirmation step to private catalog
  retrieval. On clarification the user withdrew it ("nothing, carry on, don't
  change anything"), and it was deliberately **not** recorded as a decision.
  Noted here only so a future reader knows the omission was intentional.
