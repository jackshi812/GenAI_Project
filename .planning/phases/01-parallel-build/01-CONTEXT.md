# Phase 1: Parallel Build - Context

**Gathered:** 2026-08-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Three complete technical layers, each built and verified in isolation against
mocks, with nothing wired together. Austin builds the catalog pipeline, vector
index and MCP server. Ginger builds the LangGraph nodes, LLM abstraction and
reconciliation. Jack writes the shared contract first, then speech-to-text,
text-to-speech and the Streamlit interface.

Integration is Phase 2 and is explicitly not attempted here. A layer is done
when it runs alone: Ginger's graph answers a question without Austin's server
existing, and Jack's interface renders a complete screen from `fixtures.json`
with no graph running.

Twenty-nine requirements: DOC-04, RAG-01…06, MCP-01…07, GRAPH-01…07,
VOICE-01…04, UI-01…04.

</domain>

<decisions>
## Implementation Decisions

### Reconciliation and Conflicts

- **D-01:** Every private-to-live product match receives an inspectable verdict
  through three stages: normalized title similarity, deterministic variant
  guards, then selective LLM confirmation. Scores above 0.60 auto-accept only
  when pack/count/model/size/color evidence is compatible; scores below 0.35
  reject; ambiguous or one-sided variant evidence goes to the LLM. This keeps
  per-product provenance without paying for three LLM calls on a normal turn.

- **D-02:** Disagreement is expressed as **per-field provenance**, not a single
  conflict flag. Every value on a comparison row carries where it came from —
  price from the 2020 catalog versus live, rating live-only, availability
  live-only — and fields that disagree are highlighted. This serves spec line
  143 ("citations and data lineage") directly and turns the catalog's total
  absence of ratings into a visible design decision rather than a hidden gap.

- **D-03:** A catalog product with no live match is still shown, with the live
  columns in an explicit empty state. Products are never dropped or silently
  backfilled to make the screen look complete. Many 2020 listings are delisted,
  and "this listing no longer exists" is an honest finding worth demonstrating.

- **D-04:** All reconciliation code lives in Ginger's Retriever node. Spec line
  36 assigns "reconcile conflicts" to the Retriever agent, the MCP server is
  capped at exactly two tools so reconciliation cannot become a third, and the
  graph is the only place holding both result sets at once. No new seam between
  owners.

### Live Search

- **D-05:** `web.search` wraps Serper's **shopping** endpoint, not the organic
  search endpoint. Shopping returns structured price, rating, seller and product
  link as real fields. This is the only source of ratings in the entire system —
  the private catalog has none, in any column, in any row.

- **D-06:** Live queries are built **per product** from the matched catalog
  title, roughly three per turn, rather than one category-level query. Per-field
  provenance is only meaningful if the live price was fetched for that specific
  product. The resulting call volume makes the rate limiter and per-process call
  cap load-bearing. The graded TTL cache is verified by repeating an identical
  query in Austin's MCP smoke client; because integration starts a fresh server
  process for each user turn, no plan promises a cache hit across app turns.

- **D-07:** Safety filtering is an explicit **retailer allowlist** — a short
  config list of permitted domains, with any result outside it dropped before it
  reaches the graph. Spec line 236 asks for an allowlist by name; a blocklist
  would be a weaker reading of a graded requirement.

- **D-08:** When `SERPER_API_KEY` is unset, `web.search` replays **recorded
  fixture responses** captured from real Serper calls and committed to the repo.
  Austin is unblocked immediately, the shapes are real rather than imagined,
  tests are deterministic, and the same mechanism is the **Serper-only** fallback
  when live shopping search is unavailable. ASR, LLM, and TTS may still require
  network access; the Phase 3 backup video is the full network-outage fallback.
  All owners use the same exact fixture key: first eight whitespace-delimited
  product-title words, lowercased with whitespace collapsed. A miss returns no
  result; it never falls through to a fuzzy neighbouring product.

### Contract and Team Seams

- **D-09:** The graph hands the interface products shaped as **side-by-side
  sub-objects plus a precomputed conflicts list** — `product.private{}` and
  `product.live{}` held separately, with `conflicts[]` computed by Ginger. This
  maps one-to-one onto the two-column comparison table, keeps conflict logic
  with its owner, and leaves Jack's rendering layer with no business logic.

- **D-10:** The contract is `contracts.py` using pydantic models, paired with
  `fixtures.json`. Jack writes both on day one and they are the single source of
  truth; Austin and Ginger import the models directly. The spec-required
  `price: float | str` union cannot distinguish a dirty raw price from a
  mistakenly stringified number by itself, so the contract adds a numeric-string
  validator and makes `price_low`/`price_high` strict optional floats. Those are
  the fields used by budget filtering and reconciliation, and `"17.49"` in any
  numeric slot raises before integration.

- **D-11:** One repository, everyone commits directly to `main`. Owned folders
  are disjoint (`catalog/` and `mcp_server/`, `graph/` and `prompts/`, `voice/`
  and `app/`), so genuine conflicts are confined to `contracts.py` and
  `requirements.txt`. Everyone seeing everyone's progress continuously is what
  makes the August 13 sample-output checkpoint function at all. Jack is the
  project owner and final integrator: Austin and Ginger remain responsible for
  their folders, while Jack is accountable for shared decisions, rubric
  coverage, integration acceptance, documentation, and the final demo.

- **D-12:** Briefs ship as **per-folder `CLAUDE.md` and `AGENTS.md`** with
  identical content. Claude Code auto-loads the first, Codex and Cursor auto-load
  the second, so whichever agent a teammate opens picks up the brief with no
  setup and no GSD installation on their machine. The cost is keeping two copies
  in sync.

### Demo Surface

- **D-13:** Two-column layout — conversation on the left (microphone,
  transcript, spoken answer, Play), evidence on the right. The comparison table
  is the only evidence above the fold: three compact rows with 80px images and
  Catalog (2020) beside Live, with price conflicts marked in place. The step log
  and citations follow in expanded sections below; match details are collapsed.
  This keeps reconciliation legible on a classroom projector instead of burying
  it beneath diagnostic UI.

- **D-14:** The interface shows per-field source labels, compact product images,
  and per-product match details. Match similarity, verdict and reason live in a
  collapsed expander so they remain inspectable without competing with the
  recommendation. The animated agent graph is explicitly cut: LangGraph
  `.stream()` yields after a node finishes, so presenting its latest completed
  node as “running” would be false. GRAPH-06 is satisfied by the visible step
  log after execution; Ginger does not need to emit node-start events and Jack
  does not simulate them from fixtures.

- **D-15:** Interaction is one click, then fully hands-free — click to record,
  click to stop, and transcription, graph execution and speech playback all
  follow automatically. A Play button remains for replay, satisfying spec line
  142. The known risk is browser autoplay policy blocking the first playback;
  that is accepted rather than designed around.

- **D-16:** Three canonical queries are fixed now and every owner builds and
  tests against the same ones: a **budget** query exercising the numeric
  metadata filter on private data alone, a **currency** query forcing the
  GRAPH-03 live escalation, and a **conflict** query on a product whose 2020 and
  live prices genuinely differ. The exact product picks require inspecting the
  data and are a planning task. All three are the shared acceptance set; the
  timed live demo shows the budget and conflict cases, while the currency case
  remains a focused routing check and backup query.

### Claude's Discretion

- Dependency management is a single pinned `requirements.txt` with a virtual
  environment at the repository root. Universally understood across three
  machines and adds no tooling anyone has to install on day one.
- Embedding model selection, similarity metric and threshold values, and the
  internal structure of the step log are left to research and planning.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Assignment specification — the authority on all requirements

- `Instructions.md` — the full assignment. Overrides any inference. Specific
  lines that constrain this phase:
  - §15 — LangGraph is mandatory for orchestration, no substitutions
  - §24 — fragment-based ASR/TTS is acceptable and encouraged; streaming is not required
  - §34–37 — the four required node roles: Router, Planner, Retriever, Answerer/Critic
  - §36 — "reconcile conflicts" belongs to the Retriever agent (source of D-04)
  - §73 — exactly one MCP server exposing exactly two tools, not one and not three
  - §80–88 — `web.search` return schema, verbatim
  - §99–107 — `rag.search` return schema, verbatim
  - §112–114 — MCP discovery, transport, and per-request logging requirements
  - §142 — a Play TTS button is required (source of D-15)
  - §143 — citations and data lineage including private document IDs and live links (source of D-02)
  - §149 — the LLM must be swappable via environment variable or configuration
  - §173 — Amazon Product Dataset 2020 is mandated as the primary private corpus
  - §234 — escalate to `web.search` on "current price", "availability", "now", "latest"
  - §236 — domain allowlist, respect `robots.txt` and terms of service, never log secrets (source of D-07)
  - §260–271 — the 100-point grading rubric that drives all prioritization

### Project planning

- `.planning/PROJECT.md` — core value, the eleven locked project-level
  decisions, and the dataset findings that shape this phase
- `.planning/REQUIREMENTS.md` — all 33 requirement IDs and the rubric coverage
  table mapping each rubric line to requirements
- `.planning/ROADMAP.md` — phase boundaries, the three-plan structure, success
  criteria, and the four recorded risks

### Data

- `dataset/amazon_product_data_cleaned.csv` — the working corpus Jack commits before handoff:
  10,002 rows from the mandated Amazon Product Dataset 2020 and 15 retained
  columns. It is the same row set as the Kaggle original with its thirteen
  entirely empty columns dropped.

</canonical_refs>

<code_context>
## Existing Code Insights

No application code exists. The repository currently holds `Instructions.md`,
the `dataset/` directory, and `.planning/`. Every file in this phase is new.

### Constraints standing in for existing patterns

- **The dataset dictates more than the specification does.** The Kaggle original
  had thirteen columns that were 100% empty across all 10,002 rows; the working
  cleaned CSV omits them. There is no rating column and no rating-shaped value
  anywhere in any retained field. `sku` must be derived from `Uniq Id`, which is
  fully populated and unique. `brand` must be derived from the title and must
  return null rather than guess. `ingredients` stays null — the specification
  marks it optional.
- **The specification's suggested Household Cleaning slice does not exist.** A
  keyword sweep returns 55 rows, nearly all false positives. Actual composition
  is 6,662 Toys & Games, 830 blank, 708 Home & Kitchen, 630 Clothing, 540 Sports
  & Outdoors, and a long tail. All ~10,000 rows are indexed.
- **385 rows carry malformed prices** — ranges, duplicated values, and in some
  cases raw CSS leaking into the field. RAG-02 requires parsing these to numeric
  bounds; RAG-06 requires the unparseable remainder to stay retrievable by text
  rather than being dropped.
- **Two interfaces are dictated, one is open.** The specification fixes
  `rag.search` and `web.search` return shapes verbatim, which is why Austin and
  Ginger can work without negotiating. Only the graph-to-interface shape was
  open, and D-09 closes it.

</code_context>

<specifics>
## Specific Ideas

- The August 13 sample-output checkpoint is the early-warning mechanism, not a
  status meeting. Each owner commits a real captured output — not a schema, not
  a description — and the three are checked against each other. It exists to
  catch what type annotations miss: a price serialized as a string, a brand with
  a trailing hyphen that will never match during reconciliation.

- Reconciliation is the project's differentiator and the reason the dataset's
  weaknesses are an asset. The private catalog has rich descriptions but a 2020
  price snapshot and no ratings; live shopping results have current price,
  availability and rating but little detail. Neither source answers the question
  alone, which makes reconciliation genuinely necessary rather than a contrived
  exercise — and it is a graded criterion worth ten points.

- Match confidence is displayed rather than hidden. Showing the similarity score
  and the LLM's verdict per product makes the matching inspectable, and gives an
  honest answer when a match is wrong during the demo.

- Recorded Serper fixtures serve two purposes deliberately: unblocking Austin
  before a key exists, and surviving a Serper/API failure during the live
  demonstration. They do not make ASR, the LLM, or TTS offline; the recorded
  demonstration is the fallback for a complete network outage.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 1-Parallel Build*
*Context gathered: 2026-08-10*
