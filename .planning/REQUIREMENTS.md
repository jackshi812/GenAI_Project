# Requirements — v1

Scope for the August 20, 2026 submission. Derived from `Instructions.md`, with every
requirement traceable to a line in the grading rubric.

## v1 Requirements

### Voice I/O

- [ ] **VOICE-01**: User can record a spoken request in the browser and receive a transcript without touching a keyboard
- [ ] **VOICE-02**: Transcript is displayed on screen once transcription completes
- [ ] **VOICE-03**: User can play the spoken answer back as generated audio
- [ ] **VOICE-04**: Spoken answer is capped at roughly fifteen seconds of speech

### Agent Orchestration

- [ ] **GRAPH-01**: Router extracts the task, constraints (budget, category, brand) and safety flags from a transcript
- [ ] **GRAPH-02**: Planner selects which sources to consult — private, live, or both — and builds the retrieval filter
- [ ] **GRAPH-03**: Planner escalates to live search when the request implies currency ("now", "current price", "latest", "availability")
- [ ] **GRAPH-04**: Retriever calls both MCP tools and reconciles results by SKU, brand or title similarity
- [ ] **GRAPH-05**: Answerer produces a cited recommendation, and a Critic pass rejects any claim not traceable to a source
- [ ] **GRAPH-06**: Every node execution is recorded with node name, tool invoked, timing and status
- [ ] **GRAPH-07**: LLM provider and model are read from environment configuration, not hardcoded

### Retrieval

- [ ] **RAG-01**: The full catalog is normalized and indexed with embeddings over product title and description
- [ ] **RAG-02**: Malformed price strings are parsed to numeric values, with ranges preserved as a low and high bound
- [ ] **RAG-03**: Brand is derived from the product title, returning null rather than guessing when ambiguous
- [ ] **RAG-04**: Retrieval combines vector similarity with metadata filters on price, category and brand
- [ ] **RAG-05**: Every retrieved product carries a `doc_id` usable as an on-screen citation
- [ ] **RAG-06**: Products with unparseable prices remain retrievable by text rather than being dropped

### MCP Server

- [ ] **MCP-01**: A single MCP server exposes exactly two tools over stdio transport
- [ ] **MCP-02**: Tool discovery returns both tool names with their JSON schemas
- [ ] **MCP-03**: `rag.search` returns `{sku, title, price, rating, brand, ingredients, doc_id}` per spec lines 99–107
- [ ] **MCP-04**: `web.search` returns `{title, url, snippet, price, availability}` per spec lines 81–87, sourced from a live search API
- [ ] **MCP-05**: `web.search` results are cached with a TTL between 60 and 300 seconds
- [ ] **MCP-06**: `web.search` requests are rate-limited
- [ ] **MCP-07**: Every tool request and response is logged with a timestamp and, where applicable, a source URL

### Interface

- [ ] **UI-01**: Comparison table shows the top three products with price, rating and product image
- [ ] **UI-02**: Disagreements between private and live data are visibly flagged on the affected product row
- [ ] **UI-03**: Agent step log is visible on screen during and after a run
- [ ] **UI-04**: Citations panel visually distinguishes private document IDs from live source URLs

### Documentation

- [ ] **DOC-01**: `prompts/` contains every system prompt, tool-call instruction, planner rubric and few-shot example in use
- [ ] **DOC-02**: Each prompt is explicitly mapped to the LangGraph node or tool that consumes it
- [ ] **DOC-03**: README covers setup, data preprocessing and indexing, graph design, MCP tool schemas, and safety notes
- [ ] **DOC-04**: `.env.example` lists every required variable with no real secrets committed
- [ ] **DOC-05**: Demo runs in seven minutes or less and covers architecture, results and limitations

## Rubric Coverage

| Rubric line | Points | Requirements |
|---|---:|---|
| Functionality — end-to-end voice flow, multi-agent routing, visible citations | 28 | VOICE-01…04, GRAPH-01…07, UI-04 |
| Agentic RAG Quality — accurate retrieval, grounded answers, hybrid-source use | 22 | RAG-01…06, GRAPH-04, GRAPH-05 |
| MCP Server — two working tools, discovery and schemas, caching, logging | 15 | MCP-01…07 |
| Planning and Tool Use — clear plans, conflict handling, reconciliation | 10 | GRAPH-02, GRAPH-03, GRAPH-04, UI-02 |
| UI/UX — clean app, transcript, comparison table, audio playback | 10 | VOICE-02, VOICE-03, UI-01, UI-03 |
| Presentation — demo under seven minutes, architecture, results, limitations | 10 | DOC-05 |
| Prompt Disclosure — prompts, few-shot examples, node/tool mapping | 5 | DOC-01, DOC-02 |
| **Total** | **100** | All 33 requirements mapped |

## v2 — Deferred

These are expected of a production system but not of this submission, and nothing in
the rubric rewards them.

- Streaming ASR and TTS — spec permits fragment-based processing and encourages it
- Reranking layer over retrieval results — marked optional in the spec
- Multilingual accent handling
- Review snippets in the index — the dataset carries no review data
- Persistent conversation history across turns

## Out of Scope

- **Fabricated ratings or prices** — the dataset has no ratings at all; inventing them would defeat the grounding the assignment exists to teach, and is trivially detectable
- **Replacing the mandated dataset** — spec line 173 names it as the primary corpus; its gaps are designed around instead
- **Containerization, CI, and a test suite beyond smoke checks** — ten-day timeline, none of it graded
- **Authentication, persistence, multi-user support** — single-session demo application
- **Web scraping as a search fallback** — spec line 236 requires respecting `robots.txt` and terms of service

## Traceability

| Requirement | Phase |
|---|---|
| RAG-01, RAG-02, RAG-03, RAG-04, RAG-05, RAG-06 | 1 — Parallel Build (PLAN-1, Austin) |
| MCP-01, MCP-02, MCP-03, MCP-04, MCP-05, MCP-06, MCP-07 | 1 — Parallel Build (PLAN-1, Austin) |
| GRAPH-01, GRAPH-02, GRAPH-03, GRAPH-04, GRAPH-05, GRAPH-06, GRAPH-07 | 1 — Parallel Build (PLAN-2, Ginger) |
| DOC-04 | 1 — Parallel Build (PLAN-3, Jack) |
| VOICE-01, VOICE-02, VOICE-03, VOICE-04 | 1 — Parallel Build (PLAN-3, Jack) |
| UI-01, UI-02, UI-03, UI-04 | 1 — Parallel Build (PLAN-3, Jack) |
| DOC-01, DOC-02, DOC-03, DOC-05 | 3 — Delivery |

All 33 requirements mapped to exactly one phase. Phase 2 (Integration) carries no
unique requirements — it makes the Phase 1 requirements work together.
