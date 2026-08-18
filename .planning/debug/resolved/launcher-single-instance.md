---
status: resolved
trigger: "Running python run_live_app.py again reports LiveKit UDP 7882 already in use, starts Uvicorn on 8502, and exits."
created: 2026-08-17
updated: 2026-08-17
diagnose_only: false
---

# Launcher single-instance coordination

## Symptoms

- expected_behavior: Re-running the launcher should safely reuse or deliberately restart the existing project stack without starting conflicting services.
- actual_behavior: A second launcher starts a partial stack; LiveKit cannot bind UDP 7882, Streamlit can move away from 8501, and the supervisor exits.
- error_messages: `bind: address already in use` and `A service exited unexpectedly with status 0.`
- timeline: Recurred after the previous process-only cleanup because the launcher has no persistent single-instance coordination.
- reproduction: Start `python run_live_app.py`, leave it running, then invoke the same command in another terminal.

## Current Focus

- hypothesis: Confirmed: the launcher blindly spawned services without project-scoped single-instance coordination; the first lock implementation also appended rather than replaced its state JSON.
- test: Regression tests cover exclusive ownership, state replacement, duplicate launch, verified restart, port preflight, and cleanup; real start/restart/stop cycles exercise the full stack.
- expecting: Met: the second normal invocation exits cleanly with the existing URL; `--restart` stops the recorded supervisor before starting; `--stop` shuts it down.
- next_action: None.
- reasoning_checkpoint: Use a project-specific lock and validate recorded process identities before signaling anything; never kill unrelated port owners.
- tdd_checkpoint: GREEN — 10 launcher tests and all 109 repository tests pass.

## Evidence

- timestamp: 2026-08-17T09:29:49-05:00
  observation: LiveKit PID 54693 already owns TCP 7880 and UDP 7882, while Streamlit PID 54695 already owns TCP 8501.
  implication: A complete older project stack is still live when the duplicate launcher is invoked.
- timestamp: 2026-08-17T09:35:00-05:00
  observation: `run_live_app.py` contains no PID file, file lock, port preflight, or restart/stop command and immediately spawns every service.
  implication: Duplicate startup is deterministic launcher behavior, not a transient LiveKit failure.
- timestamp: 2026-08-17T09:36:06-05:00
  observation: The first port probe treated sandbox permission denial as a free port and allowed a partial startup.
  implication: An inconclusive port probe must fail closed before spawning services.
- timestamp: 2026-08-17T09:37:30-05:00
  observation: The first lock implementation used append mode, producing concatenated JSON and preventing supervisor verification during `--restart`.
  implication: Lock state must be rewritten and truncated atomically from a non-append file descriptor.
- timestamp: 2026-08-17T09:39:25-05:00
  observation: A live duplicate invocation returned the existing URL with status 0; live `--restart` and `--stop` cycles reclaimed and freed ports 7880, 7882, and 8501 as expected.
  implication: The launcher now owns its stack lifecycle rather than relying on manual PID cleanup.
- timestamp: 2026-08-17T09:40:00-05:00
  observation: The full repository suite passed 109 tests, and the final Streamlit health endpoint returned HTTP 200.
  implication: The lifecycle fix is regression-covered and the app remains operational.

## Eliminated

- hypothesis: LiveKit is misconfigured or cannot bind on a clean launch.
  evidence: The expected LiveKit and Streamlit ports are already held by the earlier healthy project stack.

## Resolution

- root_cause: `run_live_app.py` had no project-scoped ownership record, so every invocation spawned a second LiveKit, voice-agent, and Streamlit stack even when the first was healthy.
- fix: Added an OS-backed single-instance lock with replaceable supervisor state, lock-authorized restart/stop signaling, fail-closed port preflight, fixed Streamlit port 8501, graceful SIGTERM/SIGHUP handling, and `--restart`/`--stop` commands.
- verification: 10 launcher tests pass; all 109 repository tests pass; real duplicate/start/restart/stop flows pass; final app health is HTTP 200 on port 8501.
- files_changed: `run_live_app.py`, `test_run_live_app.py`, `.planning/debug/resolved/launcher-single-instance.md`.
