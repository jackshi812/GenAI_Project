---
status: resolved
trigger: "I asked for something blue, and it returned the products thats called 'something blue' literally"
created: 2026-08-16
updated: 2026-08-16
diagnose_only: false
---

# Something blue is searched literally

## Symptoms

- expected_behavior: Interpret blue as a color preference and something as an unspecified product; choose a sensible product category or ask a useful narrowing question.
- actual_behavior: Search the literal phrase something blue and return products whose titles contain those words.
- error_messages: No exception is shown.
- timeline: Observed in the current conversational-preference build.
- reproduction: Start a fresh chat and ask for something blue.

## Current Focus

- hypothesis: Confirmed and fixed.
- test: Exact parser, fast-reply, interactive graph, live catalog smoke, and full regression suite.
- expecting: The resolved shopping context contains colors=[blue], then an agent-selected product direction supplies the product query.
- next_action: None.
- reasoning_checkpoint: The selected category is bounded to grounded catalog directions; the LLM may choose one, with a deterministic fallback after two seconds.
- tdd_checkpoint: Regression coverage added before final verification.

## Evidence

- Before the fix, `something blue` resolved to `product_query="something"` and `resolved_query="something blue"`.
- `I asked for something blue` was worse: it resolved to `product_query="asked"`, duplicated `something blue` as a feature, and searched `asked blue something`.
- After the fix, the real live-tool smoke resolves to `product_query="puzzle"`, `colors=["blue"]`, and searches `puzzle blue`.
- The real catalog smoke returned six grounded rows headed by `Deluxe Crystal Puzzle-Dragon (Blue)`.

## Eliminated

- The catalog search engine did not independently invent the literal phrase; it received that phrase from intent resolution.
- The UI product grid was not changing the query.

## Resolution

- root_cause: Generic placeholder and meta-request words survived facet stripping, while the generic `for ...` feature parser treated `something blue` as a meaningful feature. Preference-only vague requests then lacked a product direction and could reach retrieval literally.
- fix: Strip placeholder/meta words, reject feature captures containing only filler plus known facets, represent an unspecified item as `product`, and route vague preference-only requests through the bounded agent direction chooser while preserving color/size/material/texture constraints. Filter final catalog and web-only rows against explicit hard facets.
- verification: 43 focused graph tests passed; all 79 Python tests passed; 4 frontend transcript tests passed; Python compilation and `git diff --check` passed; the running app health check returned `ok`; the exact real-tool smoke searched `puzzle blue`, never `something blue`.
- files_changed: `graph/preferences.py`, `graph/fast_reply.py`, `graph/interactive.py`, `graph/decision.py`, `graph/retriever.py`, their regression tests, `prompts/decision.md`, `.env.example`.
