"""Regression tests for the one-command local launcher."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, call, patch

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


class ServiceLifecycleTests(unittest.TestCase):
    def test_only_one_launcher_can_hold_the_project_instance_lock(self) -> None:
        with TemporaryDirectory() as directory:
            state_path = Path(directory) / "live-app.json"
            first = run_live_app._InstanceLock(state_path)
            second = run_live_app._InstanceLock(state_path)
            self.addCleanup(first.close)
            self.addCleanup(second.close)

            self.assertTrue(first.try_acquire())
            first.write_state(
                {
                    "supervisor_pid": 1234,
                    "app_url": run_live_app.APP_URL,
                    "children": [],
                }
            )
            first.write_state(
                {
                    "supervisor_pid": 5678,
                    "app_url": run_live_app.APP_URL,
                    "children": [],
                }
            )

            self.assertFalse(second.try_acquire())
            self.assertEqual(second.read_state()["supervisor_pid"], 5678)

            first.release()
            self.assertTrue(second.try_acquire())

    def test_normal_second_launch_reuses_the_running_stack(self) -> None:
        instance = Mock()
        instance.try_acquire.return_value = False
        instance.read_state.return_value = {
            "supervisor_pid": 4321,
            "app_url": run_live_app.APP_URL,
            "children": [],
        }

        with patch("builtins.print") as output:
            should_start = run_live_app._coordinate_instance("start", instance)

        self.assertFalse(should_start)
        rendered = "\n".join(
            " ".join(str(part) for part in item.args) for item in output.call_args_list
        )
        self.assertIn("already running", rendered)
        self.assertIn("--restart", rendered)

    def test_restart_signals_verified_supervisor_then_takes_ownership(self) -> None:
        instance = Mock()
        instance.try_acquire.side_effect = [False, True]
        instance.read_state.side_effect = [
            {
                "supervisor_pid": 4321,
                "app_url": run_live_app.APP_URL,
                "children": [],
            },
            {},
        ]

        with (
            patch.object(run_live_app, "_pid_alive", return_value=True),
            patch.object(run_live_app.os, "kill") as kill,
        ):
            should_start = run_live_app._coordinate_instance("restart", instance)

        self.assertTrue(should_start)
        kill.assert_called_once_with(4321, run_live_app.signal.SIGTERM)
        self.assertEqual(
            instance.write_state.call_args.args[0]["supervisor_pid"],
            run_live_app.os.getpid(),
        )

    def test_port_preflight_reports_conflict_before_services_spawn(self) -> None:
        with patch.object(
            run_live_app, "_port_is_listening", side_effect=lambda port: port == 8501
        ):
            with self.assertRaisesRegex(SystemExit, "8501.*already in use"):
                run_live_app._ensure_ports_available(cloud=False)

    def test_port_probe_treats_permission_denial_as_unavailable(self) -> None:
        with patch.object(
            run_live_app.socket,
            "create_connection",
            side_effect=PermissionError("network access denied"),
        ):
            self.assertTrue(run_live_app._port_is_listening(8501))

    def test_spawn_isolates_posix_child_from_terminal_interrupts(self) -> None:
        process = Mock()
        with (
            patch.object(run_live_app.os, "name", "posix"),
            patch.object(run_live_app.subprocess, "Popen", return_value=process) as popen,
        ):
            returned = run_live_app._spawn(["example", "serve"])

        self.assertIs(returned, process)
        popen.assert_called_once_with(
            ["example", "serve"],
            cwd=run_live_app.ROOT,
            start_new_session=True,
        )

    def test_clean_interrupt_terminates_and_waits_for_every_service(self) -> None:
        processes = [Mock(), Mock(), Mock()]
        for process in processes:
            process.poll.return_value = None

        run_live_app._stop_processes(processes)

        for process in processes:
            process.terminate.assert_called_once_with()
            process.wait.assert_called_once_with(timeout=5)
            process.kill.assert_not_called()

    def test_stubborn_service_is_killed_after_grace_period(self) -> None:
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [
            run_live_app.subprocess.TimeoutExpired("service", 5),
            0,
        ]

        run_live_app._stop_processes([process])

        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual(
            process.wait.call_args_list,
            [call(timeout=5), call(timeout=2)],
        )


if __name__ == "__main__":
    unittest.main()
