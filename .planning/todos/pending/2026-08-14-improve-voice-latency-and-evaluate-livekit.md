---
created: 2026-08-14T14:56:13.120Z
title: Improve voice latency and evaluate LiveKit
area: ui
files:
  - app/main.py
  - voice/stt.py
  - voice/tts.py
  - graph/build.py
---

## Problem

Phase 2 passed end to end, but measured live turns took 35–45 seconds. The
record-then-wait experience works technically but does not feel like a
voice-to-voice agent. The professor recommended evaluating LiveKit.

## Solution

During Phase 3, benchmark the current ASR, graph-node, MCP, and TTS latency;
evaluate LiveKit before changing the architecture; and prototype the smallest
streaming or progressive-response improvement that preserves LangGraph,
grounded MCP evidence, visible citations, and the fixture fallback. Consider a
faster configured LLM and parallel or deferred non-critical work alongside
LiveKit-based streaming ASR/TTS. Record the tradeoff before adopting a new
runtime dependency.
