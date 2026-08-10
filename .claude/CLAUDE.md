<!-- GSD:project-start source:PROJECT.md -->

## Project

**Voice-to-Voice Product Discovery Assistant**

A hands-free shopping assistant. The user speaks a request — *"find me a 500 piece
puzzle under twenty dollars"* — and a LangGraph multi-agent pipeline classifies the
intent, plans which sources to consult, retrieves grounded evidence from a private
Amazon product catalog via vector search, checks live web prices when the question
warrants it, and answers out loud with citations displayed on screen.

Built as a class final project by a three-person team, due August 20, 2026. The
assignment specification lives in `Instructions.md` at the repo root and is the
authority on requirements; its grading rubric drives prioritization throughout.

**Core Value:** A spoken question returns a grounded, cited recommendation that visibly reconciles
stale private catalog data against live web data. If everything else fails, that
reconciliation — private evidence and live evidence side by side, disagreements
surfaced rather than hidden — must work.

### Constraints

- **Timeline**: Ten days, August 10 to August 20, 2026 — hard external deadline, no extension
- **Team**: Three people working simultaneously — work must partition into independent tracks, and the seams must be cheap
- **Tech stack**: LangGraph is mandatory for orchestration (spec line 15) — no substitutions
- **Tech stack**: Exactly one MCP server exposing exactly two named tools (spec line 73) — not one, not three
- **Tech stack**: LLM must be swappable via environment variable or config (spec line 149)
- **Data**: The Amazon Product Dataset 2020 is mandated as the primary private corpus (spec line 173) — swapping it risks the grade, so its gaps must be designed around rather than replaced
- **Data**: No ratings, brands, ingredients or SKUs exist in the source — derived or externally sourced values must be honest about their provenance
- **Grading**: A published rubric allocates all 100 points — scope decisions defer to it
- **Safety**: Domain allowlist, respect `robots.txt` and terms of service, never log secrets (spec line 236)

<!-- GSD:project-end -->

<!-- GSD:stack-start source:STACK.md -->

## Technology Stack

Technology stack not yet documented. Will populate after codebase mapping or first phase.
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
