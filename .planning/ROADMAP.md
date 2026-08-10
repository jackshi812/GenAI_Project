# Roadmap

**Voice-to-Voice Product Discovery Assistant** — 4 phases, 33 requirements, due August 20, 2026.

Structure is **horizontal layers**: each owner builds a complete technical layer in
isolation, and the layers are assembled near the end. Chosen because three people are
working simultaneously on a ten-day deadline, and the assignment specification
already fixes two of the three internal interfaces, which makes independent work
possible from day one.

| # | Phase | Owner | Target |
|---|---|---|---|
| 1 | Foundation | Jack | Aug 10 |
| 2 | Parallel Build | all three | Aug 11–16 |
| 3 | Integration | Ginger leads | Aug 17–18 |
| 4 | Delivery | Jack leads | Aug 19 |

---

### Phase 1: Foundation

**Goal:** Establish the shared scaffolding — repository structure, the interface
contract, mock fixtures, and environment configuration — so that three people can
build independently without colliding.

**Requirements:** DOC-04

**Owner:** Jack

**Note on concurrency:** this phase does not block Phase 2. Austin's first stretch of
work (parsing the catalog, cleaning prices, deriving brands, building the index) and
Ginger's first stretch (LLM layer, state schema, router and planner nodes) depend on
no decision made here. Both start on August 10 alongside this phase. The contract
lands before either reaches the code that consumes it.

**Success Criteria:**
1. Each owner has a folder they exclusively own, and no two owners share a file
2. `rag.search` and `web.search` return shapes are written down, matching the spec verbatim
3. A fixtures file provides realistic mock data drawn from the actual dataset, so any track can run without the others
4. `.env.example` names every required variable, with no real secrets in the repository
5. Each owner can run their own code from a clean checkout

---

### Phase 2: Parallel Build

**Goal:** Three complete, independently working layers — a data and tool layer, an
agent orchestration layer, and a voice and interface layer — each verified in
isolation against mocks.

**Requirements:** RAG-01, RAG-02, RAG-03, RAG-04, RAG-05, RAG-06, MCP-01, MCP-02,
MCP-03, MCP-04, MCP-05, MCP-06, MCP-07, GRAPH-01, GRAPH-02, GRAPH-03, GRAPH-04,
GRAPH-05, GRAPH-06, GRAPH-07, VOICE-01, VOICE-02, VOICE-03, VOICE-04, UI-01, UI-02,
UI-03, UI-04

**Plans:** three, running concurrently.

- **PLAN-1 — Austin** · `catalog/`, `mcp_server/` · catalog normalization, vector index, hybrid retrieval, MCP server with both tools, caching, rate limiting, request logging
- **PLAN-2 — Ginger** · `graph/`, `prompts/` · LLM abstraction, state schema, four cooperative nodes, reconciliation, prompt library
- **PLAN-3 — Jack** · `voice/`, `app/` · speech-to-text, text-to-speech, Streamlit interface with comparison table, conflict badges, step log and citations

**Success Criteria:**
1. A spoken-language query with a budget constraint returns correctly filtered products from the private catalog
2. Both MCP tools are callable over stdio, discovery lists them with schemas, and repeat live queries are served from cache
3. The graph runs end to end against stubbed tools and emits an answer, a step log, and a conflicts list
4. The interface renders a full result — table with images, conflict badges, step log, citations — from mock data alone
5. On August 13 each owner has committed a real captured output sample, and the three shapes have been checked against each other

---

### Phase 3: Integration

**Goal:** Replace every mock with the real component, one seam at a time, until a
spoken question produces a spoken answer through the complete system.

**Requirements:** none unique — this phase makes the Phase 2 requirements work together

**Owner:** Ginger leads, since the graph touches both neighbouring layers

**Sequence:** the two seams are done on separate days, never simultaneously. When two
seams break at once there is no way to tell which side is at fault.

1. August 17 — Austin's MCP server replaces Ginger's stubbed tools
2. August 18 — Ginger's graph replaces Jack's stubbed result

**Success Criteria:**
1. The graph retrieves from the real catalog and the real live-search tool, with no stubs remaining
2. A recorded question produces a spoken answer with citations, unassisted, end to end
3. A query that names a current price triggers live search and surfaces a real private-versus-live discrepancy on screen
4. Every product claim in the spoken answer traces to a document ID or a source URL
5. The full path runs three times consecutively without manual intervention

---

### Phase 4: Delivery

**Goal:** The submission itself — prompt disclosure, documentation, a rehearsed
demonstration, and a recorded fallback.

**Requirements:** DOC-01, DOC-02, DOC-03, DOC-05

**Owner:** Jack leads

**Success Criteria:**
1. `prompts/` contains every prompt in use, each mapped to the node or tool that consumes it
2. README covers setup, data preprocessing and indexing, graph design, MCP tool schemas, and safety notes
3. The demonstration runs under seven minutes and covers architecture, results and limitations — including the dataset's missing ratings
4. A backup recording of a successful run exists, so a network failure during the live demo is survivable
5. The repository runs from a clean clone following only the README

---

## Requirement Coverage

All 33 v1 requirements are mapped to exactly one phase.

| Phase | Count | Requirements |
|---|---:|---|
| 1 — Foundation | 1 | DOC-04 |
| 2 — Parallel Build | 28 | RAG-01…06, MCP-01…07, GRAPH-01…07, VOICE-01…04, UI-01…04 |
| 3 — Integration | 0 | — |
| 4 — Delivery | 4 | DOC-01, DOC-02, DOC-03, DOC-05 |
| **Total** | **33** | complete |

## Risks

- **Integration lands late with no slack behind it.** Mitigated by the August 13 sample-output exchange, which surfaces shape mismatches four days before they would otherwise appear.
- **The user-facing layer sits with the busiest person.** Mitigated by building the interface against fixtures from day one, so a demonstrable shell exists regardless of engine progress.
- **The live demonstration has network calls in its critical path.** Mitigated by the Phase 4 backup recording.
- **The catalog carries no ratings.** Not mitigated — it is designed around, and disclosed in the demonstration as a limitation.
