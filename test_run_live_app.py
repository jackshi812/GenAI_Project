"""Regression tests for the one-command local launcher."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import run_live_app


class ProjectInterpreterTests(unittest.TestCase):
    def test_system_python_reexecs_through_project_venv(self) -> None:
        venv_python = run_live_app.VENV_ROOT / "bin" / "python"
        with patch.object(
            run_live_app, "_project_venv_python", return_value=venv_python
        ):
            with patch.object(run_live_app.sys, "prefix", "/system/python"):
                with patch.object(run_live_app.os, "execv") as execv:
                    run_live_app._ensure_project_venv()

        execv.assert_called_once_with(
            str(venv_python),
            [
                str(venv_python),
                str(Path(run_live_app.__file__).resolve()),
                *run_live_app.sys.argv[1:],
            ],
        )

    def test_active_project_venv_does_not_reexec(self) -> None:
        venv_python = run_live_app.VENV_ROOT / "bin" / "python"
        with patch.object(
            run_live_app, "_project_venv_python", return_value=venv_python
        ):
            with patch.object(run_live_app.sys, "prefix", str(run_live_app.VENV_ROOT)):
                with patch.object(run_live_app.os, "execv") as execv:
                    run_live_app._ensure_project_venv()

        execv.assert_not_called()


if __name__ == "__main__":
    unittest.main()
