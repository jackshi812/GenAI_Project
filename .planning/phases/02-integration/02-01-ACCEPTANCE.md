# Phase 2 Integration Acceptance

Date: 2026-08-14  
Mode: `TOOL_MODE=live`, OpenAI LLM/ASR/TTS, live Serper, real stdio MCP,
local 10,002-row Chroma index

## Automated voice-path evidence

A fixed 5.144-second local speech recording asked:

> Compare the current price of the Nerf N Strike Elite Strongarm blaster with
> the catalog price.

The recording itself was temporary and was not committed or logged. Three
consecutive runs used the same recording and made no code or configuration
changes between runs.

| Run | Result | Total time | Answer audio | Live web calls |
|---|---|---:|---:|---:|
| 1 | Pass | 45.070 s | 14.016 s | 3 |
| 2 | Pass | 38.534 s | 13.608 s | 3 |
| 3 | Pass | 34.943 s | 9.312 s | 3 |

Every run passed all of these checks:

- Whisper returned a non-empty, correct Nerf Strongarm transcript.
- The graph completed at least one real `web.search` call through MCP.
- The Strongarm row contained a genuine price conflict: $13.99 in the 2020
  catalog versus $10.95 in the live result used by the graph.
- The answer included private document `AMZ-7E4E86AE` and a live eBay URL.
- The exact on-screen `answer_text` was sent to TTS without truncation.
- Measured MP3 duration was at or below 15.0 seconds.

The repeatable command is:

```bash
python -m app.phase2_acceptance path/to/question.mp3 --runs 3
```

## Live UI render evidence

Streamlit's application test runner rendered the live application with:

- zero application exceptions;
- `Source mode: Live MCP · Live Serper`;
- a visible price-conflict message;
- a private catalog citation and live URL; and
- one populated agent-step table.

## Human verification still required

The final browser-only check remains pending: grant microphone permission,
record the canonical question in Streamlit, and confirm that the transcript,
screen evidence, autoplay/player audio, and spoken answer behave correctly.
Automated audio-file testing does not prove browser microphone permissions or
autoplay policy.
