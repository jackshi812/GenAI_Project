---
status: resolved
trigger: "Streamlit CancelledError / KeyboardInterrupt traceback followed by 'A service exited unexpectedly with status 0.'"
created: 2026-08-16
updated: 2026-08-16
diagnose_only: false
---

# Launcher reports normal shutdown as a crash

## Symptoms

- expected_behavior: Ctrl+C stops Streamlit, the voice worker, and LiveKit quietly and returns success.
- actual_behavior: Streamlit prints CancelledError and KeyboardInterrupt tracebacks, then the launcher reports a status-0 child exit as unexpected.
- error_messages: `asyncio.exceptions.CancelledError`, `KeyboardInterrupt`, `Aborted!`, and `A service exited unexpectedly with status 0.`
- timeline: Observed after relaunching the updated local stack.
- reproduction: Run `python run_live_app.py`, then interrupt the foreground process.

## Current Focus

- hypothesis: Child processes share the launcher's foreground process group, so terminal SIGINT reaches Streamlit directly and races the parent's coordinated cleanup.
- test: Add lifecycle tests for child process isolation and graceful KeyboardInterrupt cleanup.
- expecting: Only the launcher handles Ctrl+C; it terminates and waits for all children without reporting a clean exit as a crash.
- next_action: None.
- reasoning_checkpoint: Terminal SIGINT must be handled by the launcher alone; service children should receive coordinated termination from the launcher.
- tdd_checkpoint: Three lifecycle regressions failed before implementation and pass afterward.

## Evidence

- The traceback contains `KeyboardInterrupt`, proving Streamlit received terminal SIGINT directly.
- The launcher treated every observed child exit, including status `0`, as unexpected.
- Before the fix, all `Popen` children inherited the launcher's foreground process group.
- A controlled post-fix start/Ctrl+C cycle printed only `Stopping local services…` and normal service shutdown logs.

## Eliminated

- This was not an application graph, Streamlit page, uvloop, or product-search failure.
- Status `0` confirms Streamlit had not crashed; it was interrupted during normal shutdown.

## Resolution

- root_cause: Child services shared the terminal signal group, so Ctrl+C interrupted Streamlit directly and raced the launcher's polling loop.
- fix: Spawn services in isolated process groups; let the launcher own Ctrl+C; terminate and wait for every child, escalating to kill only after a timeout.
- verification: Five launcher tests and the complete 89-test Python suite pass; a real interrupt cycle is traceback-free; the relaunched app health endpoint returns `ok`.
- files_changed: `run_live_app.py`, `test_run_live_app.py`.
