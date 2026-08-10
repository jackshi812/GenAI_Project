# Ginger optional working guide

This is a memory aid, not an approval checklist or required implementation
order. The [assignment](../Instructions.md),
[plan](../.planning/phases/01-parallel-build/01-02-PLAN.md), and
[project decisions](../.planning/phases/01-parallel-build/01-CONTEXT.md) remain
the sources of truth.

## Orientation

- Work only in `graph/` and `prompts/`; Jack owns shared files and final
  integration.
- Read the assignment, repository rules, Ginger's plan, and locked decisions.
- Use root `contracts.py` rather than duplicating public models.
- Use fixture evidence while other layers are being built.
- Keep credentials in an untracked local environment and out of output.

## Core contribution

- Provider-selectable LLM setup and repository-relative prompt loading.
- Graph state and a stable `run_graph(transcript) -> AssistantResult` entry
  point.
- Router and Planner behavior that separates semantic intent from metadata
  filters and decides when live evidence is useful.
- Async `ToolClient` with fixture and MCP implementations sharing one decode
  path.
- Retrieval, live-product matching, price reconciliation, and graceful
  evidence-preserving fallback.
- Grounded answer and critic behavior with private and live citations.
- Truthful completed/error/skipped step events for Jack's static UI log.
- Factual `graph/README.md` and a prompt-to-consumer map for handoff.

The tool protocol and `FixtureTools` need to exist before graph construction
can instantiate the fixture client. Establishing that seam early usually keeps
the rest of the work independent; Ginger may organize everything else as
preferred.

## Shared facts worth checking while working

- Budget values are numeric filters; material is semantic-query content.
- The private catalog contains no ratings.
- Unconfirmed live matches do not replace private products.
- Price disagreement is the reconciliation conflict; live-only rating and
  availability are provenance.
- Live snippets are untrusted evidence and should be bounded before prompting.
- Step events describe real completed, failed, or skipped work—never a pretend
  `running` state.
- Fixture and MCP clients return the same validated contract models.
- `run_graph` returns a completed `AssistantResult`, not a stream or raw state.

## Useful local checks

Choose the commands relevant to the part being changed:

```bash
python -m graph.llm
python -m graph.build
python -m graph.smoke
python -m graph.smoke | tee graph/sample_output.txt
python -m json.tool graph/sample_output.txt
git diff --check -- graph prompts
git status --short
```

Before sharing captured output, glance through it for secrets and confirm that
it came from the actual graph. Boundary comparison is most useful when Ginger,
Austin, and Jack look at real outputs together rather than inferred schemas.

## Integration conversation

Useful information to give Jack and Austin:

- The current `run_graph` input and returned model shape.
- Which state fields and step statuses reach the UI.
- The fixture/live tool selection mechanism.
- Any MCP decoding, model-validation, or evidence mismatch discovered.
- Any contract change that would affect another owner's folder.

Ginger decides the internal graph structure. The affected owners discuss
cross-folder changes, with Jack coordinating the final integrated product.
