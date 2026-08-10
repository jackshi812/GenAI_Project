# Final Project: Agentic Voice-to-Voice AI Assistant for Product Discovery

## Project Context

In e-commerce, customers often ask for product recommendations by speaking naturally—for example, “I need an eco-friendly stainless-steel cleaner under $15.” Traditional chatbots struggle to interpret intent, search private catalogs, check live availability, and answer clearly, especially in hands-free settings.

This project delivers a voice-to-voice, multi-agent assistant that:

- Understands spoken requests.
- Plans a solution path.
- Retrieves grounded evidence from a private catalog (Amazon Product Dataset 2020).
- Optionally compares private results with live web results through MCP tools.
- Replies through text-to-speech (TTS), with citations and basic safety checks.

> **Required:** Agent orchestration must be implemented with **LangGraph**.

## Project Scope

Build an AI assistant that:

- Enables voice-to-voice queries for intuitive product search and comparison.
- Uses a LangGraph multi-agent flow: **intent → plan → retrieve/tools → summarize**.
- Provides context-aware, grounded recommendations with citations to private data and any live sources.
- Supports fragment-based (non-streaming) or streaming ASR/TTS. Fragment-based processing is acceptable and encouraged for simplicity.

## Key Components

### 1. Agentic Orchestration (LangGraph)

**Objective:** Structure end-to-end reasoning as a graph of cooperative agents.

**Tasks:**

- **Router (Intent Classifier):** Extract the task, constraints (such as budget, material, and brand), and safety flags.
- **Planner:** Decide which sources to use (private, live, or both), which fields to retrieve, and which comparison criteria to apply.
- **Retriever (Agentic RAG):** Query the private catalog using vector search and metadata filters; optionally call MCP web search for live price and availability; reconcile conflicts.
- **Answerer/Critic:** Synthesize a concise, cited recommendation and enforce grounding and safety.

**Outcome:** A transparent, tool-aware pipeline with logged plans, tool inputs/outputs, and citations.

### 2. Speech Recognition (ASR)

**Objective:** Provide reliable speech-to-text transcription.

**Tasks:**

- Implement Whisper or a comparable ASR system using fragment-based recording (WAV/MP3) or streaming.
- Handle basic multilingual accents.
- Return timestamps when available.

**Outcome:** Accurate transcripts that feed the graph without requiring live streaming.

### 3. Agentic RAG (Private + Live)

**Objective:** Retrieve grounded evidence from private data and augment it with live comparisons.

**Tasks:**

- Index a curated slice of the Amazon Product Dataset 2020, such as Household Cleaning.
- Embed product titles, features, and selected top review snippets.
- Store metadata including brand, price, rating, ingredients, and category.
- Implement hybrid retrieval using vector search and metadata filters.
- Optionally add a reranker.
- Add a tool/MCP adapter for live product search and price checks.
- Reconcile SKU and brand matches, and flag discrepancies.

**Outcome:** High-precision retrieval with provenance and conflict handling.

### 4. Tool and MCP Layer

**Objective:** Safely call external services and expose private retrieval through the same protocol.

> **Required:** Build **one MCP server exposing exactly the following two required tools**.

#### `web.search`

- Wrap a legitimate web-search API, such as Brave, Serper, or Bing.
- Return:

  ```json
  {
    "title": "string",
    "url": "string",
    "snippet": "string",
    "price": "optional",
    "availability": "optional"
  }
  ```

- Rate-limit requests.
- Cache results with a TTL of 60–300 seconds.

#### `rag.search`

- Query the local vector database over the Amazon 2020 data slice.
- Return:

  ```json
  {
    "sku": "string",
    "title": "string",
    "price": "number or string",
    "rating": "number",
    "brand": "optional",
    "ingredients": "optional",
    "doc_id": "string"
  }
  ```

#### MCP Requirements

- Implement tool discovery with tool names and JSON schemas.
- Use either stdio or streamable HTTP/SSE transport.
- Log each request and response, its timestamp, and its source URL where applicable.
- Respect `robots.txt` and service terms of use.

**Outcome:** Auditable, resilient live comparisons and private retrieval through a single unified interface.

### 5. Text-to-Speech (TTS)

**Objective:** Produce clear spoken answers.

**Tasks:**

- Use fragment-based synthesis (generate a full WAV/MP3 and then play it) or streaming.
- Possible providers include OpenAI TTS/Realtime, ElevenLabs, Azure Speech, Amazon Polly, and Coqui.
- Generate a summary no longer than 15 seconds and align it with the citations shown on screen.

**Outcome:** Natural voice output without requiring live streaming.

### 6. User Interface

**Objective:** Create a simple, accessible demonstration with a hands-free flow.

**Tasks:**

- Build a Streamlit or React application.
- Include microphone capture using a record-then-send flow.
- Display the live transcript.
- Display the agent step log.
- Display a product comparison table.
- Include a **Play TTS** button.
- Show citations and data lineage, including private document IDs and live links.

**Outcome:** A clean UI that demonstrates the complete agentic workflow.

## Model-Agnostic LLM Requirement

Teams may use any commercial or open-weight LLM, provided that the model is swappable through environment variables or configuration.

Examples include:

- **Hosted:** OpenAI GPT, Anthropic Claude, Google Gemini, and AWS Bedrock providers.
- **Open-weight (local or hosted):** Llama 3.x, Mistral, Qwen, Phi-4, and TinyLlama.

### LLM Guidelines

- Keep tool use/function calling enabled.
- Limit context to grounded snippets.
- Require citations to reduce hallucinations.
- Log prompts and system messages for transparency. See [Prompt Disclosure](#prompt-disclosure).

## Example Voice Interaction

> **User (voice):** “Recommend an eco-friendly stainless-steel cleaner under fifteen dollars.”
>
> **System (voice):** “Here are three options that fit your budget and material. My top pick is Brand X Steel-Safe Eco Cleaner—plant-based surfactants, 4.6★ average rating, typically $12.49. I compared this with two alternatives. I’ve sent details and sources to your screen. Would you like the most affordable or the highest rated?”

The screen should show a top-three comparison table containing price, rating, and ingredients, with citations to private document IDs and live links.

## Data

Use the **Amazon Product Dataset 2020 (Kaggle)** as the primary private corpus.

### Target Schemas

#### `products.parquet`

| Field | Description |
|---|---|
| `id` | Product identifier |
| `title` | Product title |
| `brand` | Product brand |
| `category` | Product category |
| `price` | Product price |
| `rating` | Average rating |
| `features` | Product features |
| `ingredients` | Product ingredients |

#### `reviews.parquet` (Optional)

| Field | Description |
|---|---|
| `product_id` | Related product identifier |
| `stars` | Review rating |
| `summary/snippets` | Review summary or selected snippets |

### Indexing Requirements

- Create embeddings from the title, features, and selected review snippets.
- Store the embeddings in FAISS or Chroma.
- Normalize units, such as price per ounce, to support fair comparisons.

## Expected Deliverables

### Voice-to-Voice Assistant

- Multi-agent LangGraph pipeline.
- Private RAG plus at least one MCP-based web comparison.
- Spoken responses with on-screen citations.

### User Interface

- Streamlit or React app.
- Microphone input through recording or file upload.
- Transcript display.
- Agent step log.
- Product comparison table.
- Fragment-based TTS playback.

### Documentation

- Data preprocessing and indexing instructions.
- Graph design.
- MCP server and tool schemas.
- Safety notes.
- Setup instructions and `.env.example`.
- Run scripts.

## Implementation Guidance

- **`web.search`:** Call a web-search API; normalize the response to `{title, url, snippet, price?, availability?}`; cache responses; include source URLs.
- **`rag.search`:** Use vector search and metadata filters over the Amazon 2020 slice; return `doc_id` values for citations; optionally rerank results.
- **Planner:** Prefer `rag.search` for factual product information. If the user asks for “current price,” “availability,” “now,” or “latest,” also call `web.search`. Reconcile results using SKU, brand, or title similarity.
- **ASR/TTS:** Implement fragment-based processing first: record → transcribe, then synthesize → play. Add streaming only if desired.
- **Safety:** Use a domain allowlist; respect `robots.txt` and terms of use; avoid unsafe chemical advice; never log secrets.

## Milestones

### Checkpoint 1 — Week 6

- One-page proposal covering the problem, data slice, and tools.
- Ingestion notebook.
- Brief related-work review.

### Checkpoint 2 — Week 8

- Architecture diagram showing the graph and MCP calls.
- UI wireframe.
- RAG evaluation plan.
- MCP README containing tool schemas.

### Final — Week 10

- Live demo of no more than seven minutes.
- Repository with clean code and a README.
- Build scripts for the index and MCP server.
- One short presentation.

## Grading Rubric (100 Points)

| Category | Points | Criteria |
|---|---:|---|
| Functionality | 28 | End-to-end voice flow, multi-agent routing, and visible citations |
| Agentic RAG Quality | 22 | Accurate retrieval, grounded answers, and sensible hybrid-source use |
| MCP Server | 15 | Two working tools, discovery and schemas, caching, and logging |
| Planning and Tool Use | 10 | Clear plans, conflict handling, and reconciliation |
| UI/UX | 10 | Clean app, transcript, comparison table, and audio playback |
| Presentation | 10 | Clear and engaging demo of no more than seven minutes, covering architecture, results, and limitations |
| Prompt Disclosure | 5 | Key prompts, system prompts, router/planner tool prompts, few-shot examples, and prompt-to-node/tool mapping |
| **Total** | **100** | |

## Prompt Disclosure

> **Required:** Submit either a `prompts/` folder or a dedicated README section containing:

- Main system prompts.
- Tool-call instructions.
- Planner rubric.
- Any few-shot examples used by agents.
- A clear mapping between prompts and their corresponding LangGraph nodes/tools.
