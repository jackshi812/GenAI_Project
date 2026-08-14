# Graph folder brief

This folder is owned and maintained by Jack. It holds the LangGraph orchestration layer:
state schema, the Router / Planner / Retriever / Answerer-Critic nodes, the
tool-client seam, and the public `run_graph(transcript) -> AssistantResult`
entry point.

Rules that bind all work here:

- **All reconciliation logic lives in this folder's Retriever node** — never in
  the MCP server (D-04, spec §36). The MCP server is capped at exactly two
  tools; reconciliation cannot become a third.
- **UI-facing models live in `contracts.py` at the repo root and are imported,
  never redefined** (D-10). Graph-internal models (`RouterOutput`,
  `PlannerOutput`) live in `graph/state.py`.
- **Every completed or failed node and tool call records a `StepEvent`** for
  the visible step log (D-14). No fabricated `running` states — the UI renders
  completed history only.
- Prompts live in `prompts/*.md`, each opening with a "consumed by" comment
  naming its node (Prompt Disclosure, spec §273–282).
- Never invent a price, rating, availability claim, citation, or match. The
  private catalog has no ratings; ratings come only from live evidence.
- Never commit `.env`; never print or log an API key.
