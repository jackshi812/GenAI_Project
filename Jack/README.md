# Jack — project owner, voice, UI, and integration

This folder is a practical handoff packet, not an implementation directory.
Jack writes product code in `voice/`, `app/`, and shared files at the repository
root.

Jack is accountable for helping the three parts become one coherent project.
That does not make him the technical approver for every choice: Austin and
Ginger are free to design their own internals as long as the shared interfaces
remain compatible and the assignment requirements are covered.

## Ownership

| Contributor | Main area | Collaboration expectation |
|---|---|---|
| **Jack** | `voice/`, `app/`, repository root | Maintain shared artifacts, connect the layers, and shape the final experience. |
| **Austin** | `catalog/`, `mcp_server/` | Choose the catalog and server implementation; share stable tool inputs and outputs. |
| **Ginger** | `graph/`, `prompts/` | Choose the graph and prompt implementation; preserve the agreed graph-to-UI result. |

Avoid editing another contributor's area without discussing it first. When a
cross-layer issue appears, solve it together at the interface rather than
taking over the other component.

## Reference documents

- [Instructions.md](../Instructions.md) is the assignment specification and
  highest authority.
- [Jack's plan](../.planning/phases/01-parallel-build/01-03-PLAN.md) contains
  the detailed rubric mapping and implementation ideas.
- [Shared context](../.planning/phases/01-parallel-build/01-CONTEXT.md) records
  decisions D-01 through D-16.
- [Integration plan](../.planning/phases/02-integration/02-01-PLAN.md) and
  [delivery plan](../.planning/phases/03-delivery/03-01-PLAN.md) provide more
  detail when the team reaches those stages.

Treat the plans as guidance for reaching the rubric, not as a ban on sensible
implementation choices. Discuss any change that affects a shared shape, tool
name, source claim, or user-visible behavior.

## Shared starting point

Jack maintains the artifacts that let everyone work independently:

- `contracts.py` — the common pydantic models used across graph, tools, and UI;
- `fixtures.json` — real catalog-backed examples for the graph and interface;
- `serper_fixtures.json` and `record_serper_fixtures.py` — recorded shopping
  responses for the no-key path;
- `.env.example`, `.gitignore`, and `requirements.txt` — shared setup;
- the cleaned dataset tracked at
  `dataset/amazon_product_data_cleaned.csv`.

The shared models are `RagResult`, `WebResult`, `MatchInfo`, `Conflict`,
`ComparisonProduct`, `StepEvent`, `Citation`, and `AssistantResult`. Austin and
Ginger should import these rather than maintain parallel definitions. The team
can refine optional internal fields together; changes to the public shapes
should be announced because all three layers consume them.

Nobody needs to wait for a finished neighboring component. Austin can replay
recorded Serper data, Ginger can use fixture tools, and Jack can render a
fixture `AssistantResult`. Integration should replace those seams rather than
redesign the components.

## Jack's product work

### Voice interaction

Build the simplest reliable spoken loop:

1. capture microphone audio;
2. transcribe it;
3. show the transcript so the user can see what was understood;
4. send the transcript to the result provider;
5. synthesize the returned answer; and
6. play it automatically while keeping an audio control available for replay.

The plan suggests small `voice/stt.py` and `voice/tts.py` modules. Jack may
organize the code differently if `app/main.py` still has a clear transcription
and synthesis seam. Keep spoken answers within the assignment's voice-duration
limit and make empty audio or API failures understandable to the user.

### Interface

The interface should make the project easy to understand during one short live
conversation. A useful default is:

- left side: recorder, transcript, answer text, and audio playback;
- right side: the private-versus-live comparison table near the top;
- below it: truthful completed step events and citations;
- collapsed details: title-match confidence and reasoning.

The comparison is the main story. Show the private catalog value beside the
live value, highlight a genuine price disagreement on its product row, and
label missing live matches honestly. Ratings are live-only evidence, not a
conflict with the private catalog. Jack has freedom over styling, components,
and layout as long as the spoken flow and reconciliation remain legible on a
projector.

LangGraph streaming does not reveal a node before it runs, so do not imply a
fake live animation. A static flow plus the completed step log is honest and
less work.

### Result seam

Keep one replaceable result provider in the UI:

```python
load_result(transcript: str) -> AssistantResult
```

It can read fixtures while the team works independently and later delegate to
Ginger's stable public call:

```python
run_graph(transcript: str) -> AssistantResult
```

The UI should render the returned contract rather than reproduce matching,
reconciliation, or retrieval logic.

## Compatibility points for the team

- Austin's MCP server exposes `rag.search` and `web.search` over stdio.
- Ginger's tool client consumes those two tools and returns validated shared
  models to the graph.
- The shared replay key is the first eight whitespace-delimited product-title
  words, lowercased with whitespace collapsed.
- Private citations use catalog document IDs; live citations use real source
  URLs.
- Source-mode labels distinguish live MCP/live Serper, live MCP/recorded
  Serper, and fixture graph/recorded data.
- The catalog contains no ratings or ingredients. Never fill either with a
  plausible-looking value.
- Numeric budget constraints belong in metadata filters, not embedding text.

These are compatibility facts, not instructions about class layout or coding
style. Contributors can choose their own internal design.

## Environment

Keep real credentials only in an ignored local `.env`. The planned code reads
`os.environ`, so load the file into each fresh terminal used for credentialed
commands:

```bash
set -a
source .env
set +a
```

Never commit or display a key. Recorded Serper data is an honest fallback for
the shopping call; it does not mean ASR, LLM, or TTS are offline.

## A flexible working rhythm

One reasonable sequence is:

1. share contracts, fixtures, configuration, and the dataset;
2. build voice and UI against fixtures while teammates build their layers;
3. compare one real output from each layer and resolve shape differences;
4. connect Ginger's graph to Austin's server, then connect Jack's UI to the
   graph;
5. rehearse the voice-to-voice flow and simplify anything hard to explain; and
6. assemble documentation, presentation material, and a backup recording.

This sequence is a coordination aid. The team can rearrange work when another
order is more efficient, provided shared changes are communicated early.

## What Jack should optimize for

The final experience should let a grader hear a question, see the recognized
transcript, understand why private or live tools were used, compare historical
and current evidence, hear a concise grounded answer, and inspect its sources.
Favor a reliable, understandable path over extra architecture.

[CHECKLIST.md](CHECKLIST.md) is an optional coordination guide, not an approval
or pass/fail checklist.
