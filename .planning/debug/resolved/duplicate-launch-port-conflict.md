---
status: resolved
trigger: "Second run binds Streamlit to 8502 and LiveKit reports UDP 7882 already in use."
created: 2026-08-16
updated: 2026-08-16
diagnose_only: false
---

# Duplicate local stack port conflict

## Symptoms

- expected_behavior: The user's launcher owns the normal local ports and serves the app on 8501.
- actual_behavior: LiveKit cannot bind UDP 7882 and Streamlit falls forward to 8502 before the launcher exits.
- error_messages: `bind: address already in use` and `A service exited unexpectedly with status 0.`
- timeline: Occurred while a prior assistant-launched stack was still running.
- reproduction: Start a second `run_live_app.py` while the first stack owns ports 7880, 7882, and 8501.

## Current Focus

- hypothesis: Confirmed duplicate process stack.
- test: Inspect listeners before and after coordinated shutdown.
- expecting: Existing project processes own the conflicting ports; stopping that stack frees them.
- next_action: None.
- reasoning_checkpoint: Do not kill unrelated processes; stop only the known launcher session.
- tdd_checkpoint: Not applicable; external process-state collision.

## Evidence

- LiveKit PID 20708 owned UDP 7882 and TCP 7880.
- Streamlit PID 20710 owned TCP 8501.
- Both were children of the previously launched project stack.
- After coordinated shutdown, no listeners remain on 7880, 7882, 8501, or 8502.

## Eliminated

- No new application-code failure occurred.
- Port 8502 was Streamlit's automatic fallback, not the intended app address.

## Resolution

- root_cause: Two local project stacks were launched simultaneously.
- fix: Gracefully stopped the earlier background launcher and its exact children.
- verification: All required local ports are free for the user's foreground launch.
- files_changed: None; process state only.
