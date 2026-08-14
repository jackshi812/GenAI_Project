# MCP server folder brief

- Jack owns and maintains every implementation file in this folder.
- This folder contains one stdio MCP server for product evidence.
- The assignment requires exactly two tools: `rag.search` and `web.search`.
- Do not add a third tool without changing the assignment architecture.
- `rag.search` wraps the project's private catalog retrieval.
- `web.search` uses Serper Shopping or exact recorded Serper fixtures.
- Reconciliation belongs in the graph Retriever node, not this server.
- Tool discovery must expose explicit JSON input schemas.
- stdout is reserved exclusively for MCP protocol traffic.
- Send operational details to JSONL logs or stderr.
- Log requests, responses, timing, counts, and live source URLs.
- Never log API keys, tokens, secrets, or environment values.
- Filter live evidence to the retailer allowlist before returning it.
- `mcp_server/logs/` is generated locally and must not be committed.
- Keep `CLAUDE.md` and `AGENTS.md` byte-identical.
