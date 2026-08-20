---
status: resolved
trigger: "mix ammonia with vineager doesnt trigger safety warning. Also sometimes I say I don't like it, the system doesn't ask me what I want instead"
created: 2026-08-20
updated: 2026-08-20T18:46:45Z
diagnose_only: false
---

# Ammonia-vinegar safety and rejection recovery

## Symptoms

- expected_behavior: A request to mix ammonia with vinegar, including the spoken misspelling "vineager", immediately returns a safety warning without product retrieval. A bare rejection such as "I don't like it" consistently asks what the shopper wants instead.
- actual_behavior: The ammonia-vinegar request can continue as a shopping query without a warning. Bare rejection handling is intermittent and can fail to ask a recovery question.
- error_messages: No exception was reported; both failures are semantic routing omissions.
- timeline: Unknown; reproduced in the current system.
- reproduction: Say "mix ammonia with vineager". In a later turn with prior results, say "I don't like it".

## Current Focus

- hypothesis: CONFIRMED — the safety pair and voice-preview omissions caused the warning failure, while preference-model output could override a correctly recognized bare rejection.
- test: The exact RED regressions now pass in the fast voice path and both graph modes; the adjacent graph suite also passes.
- expecting: Met — no retrieval occurs, a fixed safety warning is returned, and bare rejection always asks what the shopper would like instead.
- next_action: None; resolved and regression-covered.
- reasoning_checkpoint:
    hypothesis: "A shared deterministic guard must run before models and tools, and bare rejection must bypass preference interpretation."
    confirming_evidence:
      - "The fast safety test originally reached catalog search."
      - "The interactive typo case originally called rag.search('mix ammonia')."
      - "An adversarial preference result originally changed the rejection into a search turn."
    falsification_test: "The hypothesis would be wrong if the same unchanged tests still searched after only the pre-model guards were added."
    fix_rationale: "One shared detector keeps fast, interactive, and LLM graph paths consistent; deterministic rejection wording removes model-dependent recovery."
    blind_spots: "No live microphone session was run; behavior is verified at the voice-preview and graph boundaries."
- tdd_checkpoint:
    test_files:
      - graph/test_fast_reply.py
      - graph/test_interactive.py
      - graph/test_response_style.py
    status: green
    test_count: 68
    failure_count: 0
    failure_output: "Initial focused run: 5 selectors produced 6 failures/subtest failures. Final adjacent run: 68 tests passed."

## Evidence

- timestamp: 2026-08-20T00:00:00Z
  observation: `graph/interactive.py::_HAZARDOUS_MIX` requires bleach or chlorine paired with ammonia, acid, or vinegar; ammonia plus vinegar cannot match, and "vineager" is not recognized.
  implication: The exact reported safety phrase deterministically misses the default interactive graph gate.
- timestamp: 2026-08-20T00:00:00Z
  observation: `graph/fast_reply.py::build_fast_reply` has no hazardous-mixing branch before catalog search.
  implication: Voice sessions can emit a non-safety preview even when the later full graph recognizes a hazardous pair.
- timestamp: 2026-08-20T00:00:00Z
  observation: Both graph routers call `resolve_preferences` before deciding that a rejection is a refinement, and count model-produced `preference_changed` as actionable.
  implication: A pure rejection can be routed differently depending on preference-model output, explaining the intermittent behavior.
- timestamp: 2026-08-20T18:40:00Z
  observation: The initial focused run failed all five selectors: the fast path searched, the interactive typo case called `rag.search('mix ammonia')`, the preference parser was awaited, and recovery wording was not the requested question.
  implication: The regressions independently reproduced both reported failures before production changes.
- timestamp: 2026-08-20T18:46:45Z
  observation: All 68 adjacent tests pass, plus the exact safety regression passes under both `interactive` and `llm` graph modes; `git diff --check` is clean.
  implication: The shared guard works across every active response path without regressing adjacent dialogue and recommendation behavior.

## Eliminated

## Resolution

- root_cause: Safety recognition lived only in the interactive router and required bleach/chlorine, so ammonia plus vinegar and the ASR spelling "vineager" missed; the fast voice response had no guard. Separately, pure rejection entered preference resolution before refinement routing, so an LLM-produced `preference_changed=True` could suppress the follow-up question.
- fix: Added a shared pre-model safety detector and fixed warning used by fast, interactive, and LLM graph paths; included ammonia-vinegar and common spoken spelling variants. Bare rejection now preserves prior context, skips preference parsing, pauses tools, and deterministically asks what the shopper would like instead.
- verification: Focused RED-to-GREEN completed. Adjacent suite: 68/68 passing in 1.558 seconds. Exact safety test also passes in both graph modes. Python compilation and `git diff --check` pass.
- files_changed:
    - graph/safety.py
    - graph/nodes.py
    - graph/interactive.py
    - graph/fast_reply.py
    - graph/response_style.py
    - graph/test_fast_reply.py
    - graph/test_interactive.py
    - graph/test_response_style.py
    - prompts/router.md
    - prompts/dialogue.md
