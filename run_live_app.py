"""Launch the local LiveKit server, voice agent, and Streamlit app together."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import IO, Any

if os.name == "nt":  # pragma: no cover - exercised on Windows only
    import msvcrt
else:  # pragma: no branch - this project is normally run on macOS/Linux
    import fcntl

ROOT = Path(__file__).resolve().parent
VENV_ROOT = ROOT / ".venv"
APP_URL = "http://localhost:8501"
_PROJECT_KEY = hashlib.sha256(str(ROOT).encode("utf-8")).hexdigest()[:12]
INSTANCE_STATE_PATH = (
    Path(tempfile.gettempdir()) / f"genai-project-live-app-{_PROJECT_KEY}.json"
)


class _InstanceLock:
    """A project-scoped process lock with a small readable state document."""

    def __init__(self, path: Path = INSTANCE_STATE_PATH) -> None:
        self.path = path
        self._handle: IO[str] | None = None
        self.acquired = False

    def _open(self) -> IO[str]:
        if self._handle is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_RDWR | os.O_CREAT
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            descriptor = os.open(self.path, flags, 0o600)
            self._handle = os.fdopen(descriptor, "r+", encoding="utf-8")
            self._handle.seek(0, os.SEEK_END)
            if self._handle.tell() == 0:
                # Windows locks a byte range; reserving byte zero also works as
                # harmless leading whitespace in the JSON state file.
                self._handle.write(" ")
                self._handle.flush()
        return self._handle

    def try_acquire(self) -> bool:
        """Acquire ownership without blocking; return False when already owned."""
        if self.acquired:
            return True
        handle = self._open()
        try:
            if os.name == "nt":  # pragma: no cover - Windows only
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            if isinstance(exc, BlockingIOError) or exc.errno in {
                errno.EACCES,
                errno.EAGAIN,
                errno.EDEADLK,
            }:
                return False
            raise
        self.acquired = True
        return True

    def read_state(self) -> dict[str, Any]:
        handle = self._open()
        handle.seek(0)
        raw = handle.read().strip()
        if not raw:
            return {}
        try:
            state = json.loads(raw)
        except (json.JSONDecodeError, OSError):
            return {}
        return state if isinstance(state, dict) else {}

    def write_state(self, state: dict[str, Any]) -> None:
        if not self.acquired:
            raise RuntimeError("Cannot update launcher state without owning its lock.")
        handle = self._open()
        handle.seek(0)
        handle.write(" " + json.dumps(state, sort_keys=True))
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())

    def release(self) -> None:
        if not self.acquired or self._handle is None:
            return
        if os.name == "nt":  # pragma: no cover - Windows only
            self._handle.seek(0)
            msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self.acquired = False

    def close(self) -> None:
        self.release()
        if self._handle is not None:
            self._handle.close()
            self._handle = None


def _project_venv_python() -> Path | None:
    """Return this repository's virtualenv interpreter when available."""
    candidates = (
        VENV_ROOT / "bin" / "python",
        VENV_ROOT / "Scripts" / "python.exe",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _ensure_project_venv() -> None:
    """Re-run the launcher inside .venv when invoked by a system Python."""
    venv_python = _project_venv_python()
    if venv_python is None or Path(sys.prefix).resolve() == VENV_ROOT.resolve():
        return
    print(f"Using project environment: {VENV_ROOT}", flush=True)
    os.execv(
        str(venv_python),
        [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
    )


def _cloud_configured() -> bool:
    names = ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")
    values = [bool(os.getenv(name, "").strip()) for name in names]
    if any(values) and not all(values):
        raise SystemExit(f"Set {', '.join(names)} together, or leave all three blank.")
    return all(values)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _state_for() -> dict[str, Any]:
    return {
        "supervisor_pid": os.getpid(),
        "app_url": APP_URL,
        "root": str(ROOT),
    }


def _wait_for_lock(instance: _InstanceLock, timeout: float = 20) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if instance.try_acquire():
            return True
        time.sleep(0.1)
    return instance.try_acquire()


def _coordinate_instance(action: str, instance: _InstanceLock) -> bool:
    """Return True only when this invocation should start the service stack."""
    if instance.try_acquire():
        if action == "stop":
            instance.write_state({})
            print("Live voice app is not running.")
            return False
        instance.write_state(_state_for())
        return True

    state = instance.read_state()
    app_url = str(state.get("app_url") or APP_URL)
    if action == "start":
        print(f"Live voice app is already running at {app_url}.")
        print("To reload code changes: python run_live_app.py --restart")
        print("To stop it: python run_live_app.py --stop")
        return False

    try:
        supervisor_pid = int(state.get("supervisor_pid", 0))
    except (TypeError, ValueError):
        supervisor_pid = 0
    if not _pid_alive(supervisor_pid):
        raise SystemExit(
            "Another process holds the project launcher lock, but its supervisor "
            "is unavailable. Stop it from its original terminal."
        )

    verb = "Restarting" if action == "restart" else "Stopping"
    print(f"{verb} the existing live voice app…", flush=True)
    os.kill(supervisor_pid, signal.SIGTERM)
    if not _wait_for_lock(instance):
        raise SystemExit(
            "The existing launcher did not stop within 20 seconds. Press Ctrl+C "
            "in its original terminal, then try again."
        )

    if action == "stop":
        instance.write_state({})
        print("Live voice app stopped.")
        return False
    instance.write_state(_state_for())
    return True


def _port_is_listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except PermissionError:
        # A restricted runtime cannot prove the port is free. Fail closed so
        # the launcher never starts a partial stack after an inconclusive probe.
        return True
    except OSError:
        return False


def _ensure_ports_available(cloud: bool) -> None:
    ports = [8501] if cloud else [7880, 8501]
    occupied = [port for port in ports if _port_is_listening(port)]
    if not occupied:
        return
    rendered = ", ".join(str(port) for port in occupied)
    raise SystemExit(
        f"Cannot start because port(s) {rendered} are already in use by an "
        "untracked process. If this is an older app terminal, press Ctrl+C "
        "there once and rerun this command."
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--restart",
        action="store_const",
        const="restart",
        dest="action",
        help="stop the existing project stack and launch a fresh one",
    )
    actions.add_argument(
        "--stop",
        action="store_const",
        const="stop",
        dest="action",
        help="stop the existing project stack without starting another",
    )
    parser.set_defaults(action="start")
    return parser.parse_args(argv)


def _raise_keyboard_interrupt(_signum: int, _frame: Any) -> None:
    raise KeyboardInterrupt


def _install_shutdown_handlers() -> None:
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, _raise_keyboard_interrupt)


def _spawn(command: list[str]) -> subprocess.Popen:
    """Start one service outside the launcher's terminal signal group."""
    kwargs: dict = {"cwd": ROOT}
    if os.name == "nt":
        creation_flag = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        if creation_flag:
            kwargs["creationflags"] = creation_flag
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(command, **kwargs)


def _stop_processes(processes: list[subprocess.Popen]) -> None:
    """Stop every child quietly, escalating only when graceful exit stalls."""
    running = [process for process in processes if process.poll() is None]
    for process in running:
        process.terminate()
    for process in running:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass


def main(argv: list[str] | None = None) -> None:
    _ensure_project_venv()
    args = _parse_args(argv)
    instance = _InstanceLock()
    processes: list[subprocess.Popen] = []
    owns_stack = False
    try:
        should_start = _coordinate_instance(args.action, instance)
        if not should_start:
            return
        owns_stack = True

        # Import project dependencies only after selecting the project interpreter.
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        cloud = _cloud_configured()
        _ensure_ports_available(cloud)
        _install_shutdown_handlers()
        commands: list[list[str]] = []
        if not cloud:
            if shutil.which("livekit-server") is None:
                raise SystemExit(
                    "livekit-server is required for local mode. On macOS: "
                    "brew install livekit"
                )
            commands.append(["livekit-server", "--dev"])
            agent_module = "voice.local_livekit"
        else:
            agent_module = "voice.livekit_agent"

        commands.extend(
            [
                [sys.executable, "-m", agent_module, "dev"],
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    "app/main.py",
                    "--server.headless",
                    "true",
                    "--server.port",
                    "8501",
                ],
            ]
        )

        for command in commands:
            processes.append(_spawn(command))
        print(f"Live voice app: {APP_URL}")
        print("Press Ctrl+C to stop all services.")
        while True:
            for process in processes:
                return_code = process.poll()
                if return_code is not None:
                    raise SystemExit(
                        f"A service exited unexpectedly with status {return_code}."
                    )
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping local services…", flush=True)
    finally:
        try:
            if owns_stack:
                try:
                    _stop_processes(processes)
                finally:
                    if instance.acquired:
                        instance.write_state({})
        finally:
            instance.close()


if __name__ == "__main__":
    main()
