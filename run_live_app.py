"""Launch the local LiveKit server, voice agent, and Streamlit app together."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_ROOT = ROOT / ".venv"


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


def main() -> None:
    _ensure_project_venv()

    # Import project dependencies only after selecting the project interpreter.
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    cloud = _cloud_configured()
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
            ],
        ]
    )

    processes: list[subprocess.Popen] = []
    try:
        for command in commands:
            processes.append(subprocess.Popen(command, cwd=ROOT))
        print("Live voice app: http://localhost:8501")
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
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()


if __name__ == "__main__":
    main()
