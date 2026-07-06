"""Tests for the no-shell command execution tool."""

import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from min_agent.command_registry import (
    CommandDefinition,
    CommandRegistry,
    build_default_command_registry,
)
from min_agent.tools.command import run_command
from min_agent.types import ToolResult


def _fake_runner_success(
    args, *, cwd, capture_output, text, timeout, shell, check
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=args,
        returncode=0,
        stdout="2026-07-03 10:30:21 CST\n",
        stderr="",
    )


def _fake_runner_timeout(
    args, *, cwd, capture_output, text, timeout, shell, check
) -> subprocess.CompletedProcess[str]:
    raise subprocess.TimeoutExpired(cmd=args, timeout=timeout)


def _fake_runner_nonzero(
    args, *, cwd, capture_output, text, timeout, shell, check
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=args,
        returncode=1,
        stdout="",
        stderr="date: invalid option",
    )


def _fake_runner_file_not_found(
    args, *, cwd, capture_output, text, timeout, shell, check
) -> subprocess.CompletedProcess[str]:
    raise FileNotFoundError("No such file: /bin/date")


def _fake_runner_os_error(
    args, *, cwd, capture_output, text, timeout, shell, check
) -> subprocess.CompletedProcess[str]:
    raise OSError("Permission denied")


class CommandToolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_default_command_registry()
        self.workspace = Path("/tmp/test-workspace")

    def test_successful_execution_strips_trailing_newline(self) -> None:
        captured: dict = {}

        def capture_runner(
            args, *, cwd, capture_output, text, timeout, shell, check
        ) -> subprocess.CompletedProcess[str]:
            captured["args"] = args
            captured["cwd"] = cwd
            captured["shell"] = shell
            captured["timeout"] = timeout
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout="2026-07-03 10:30:21 CST\n",
                stderr="",
            )

        result = run_command(
            self.workspace,
            {"command_id": "get_current_time"},
            self.registry,
            runner=capture_runner,
        )
        self.assertTrue(result.success)
        self.assertEqual(
            captured["args"], ["/bin/date", "+%Y-%m-%d %H:%M:%S %Z"]
        )
        self.assertEqual(captured["cwd"], str(self.workspace))
        self.assertFalse(captured["shell"])
        self.assertEqual(captured["timeout"], 5.0)
        self.assertEqual(result.metadata["exit_code"], 0)
        self.assertEqual(result.content, "2026-07-03 10:30:21 CST")

    def test_unknown_command_id_rejected_before_runner(self) -> None:
        runner = MagicMock()
        result = run_command(
            self.workspace,
            {"command_id": "nonexistent"},
            self.registry,
            runner=runner,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "unknown_command_id")
        runner.assert_not_called()

    def test_timeout_produces_structured_error(self) -> None:
        result = run_command(
            self.workspace,
            {"command_id": "get_current_time"},
            self.registry,
            runner=_fake_runner_timeout,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "command_timeout")
        self.assertTrue(result.metadata["timed_out"])

    def test_nonzero_exit_produces_failure(self) -> None:
        result = run_command(
            self.workspace,
            {"command_id": "get_current_time"},
            self.registry,
            runner=_fake_runner_nonzero,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.metadata["exit_code"], 1)
        self.assertEqual(result.metadata["stderr"], "date: invalid option")
        self.assertIn("exit_code=1", result.content)

    def test_file_not_found_produces_start_failed(self) -> None:
        result = run_command(
            self.workspace,
            {"command_id": "get_current_time"},
            self.registry,
            runner=_fake_runner_file_not_found,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "command_start_failed")

    def test_os_error_produces_start_failed(self) -> None:
        result = run_command(
            self.workspace,
            {"command_id": "get_current_time"},
            self.registry,
            runner=_fake_runner_os_error,
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "command_start_failed")

    def test_stdout_truncation_keeps_prefix(self) -> None:
        original_stdout = "STDOUT-BEGIN-" + ("x" * 5000) + "-STDOUT-END"
        original_stderr = "STDERR-BEGIN-" + ("y" * 5000) + "-STDERR-END"

        def long_output_runner(
            args, *, cwd, capture_output, text, timeout, shell, check
        ) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=original_stdout,
                stderr=original_stderr,
            )

        result = run_command(
            self.workspace,
            {"command_id": "get_current_time"},
            self.registry,
            runner=long_output_runner,
        )
        self.assertEqual(result.metadata["stdout"], original_stdout[:4096])
        self.assertEqual(result.metadata["stderr"], original_stderr[:4096])
        self.assertTrue(result.metadata["stdout"].startswith("STDOUT-BEGIN-"))
        self.assertTrue(result.metadata["stderr"].startswith("STDERR-BEGIN-"))
        self.assertTrue(result.metadata["stdout_truncated"])
        self.assertTrue(result.metadata["stderr_truncated"])

    def test_metadata_contains_all_required_fields(self) -> None:
        result = run_command(
            self.workspace,
            {"command_id": "get_current_time"},
            self.registry,
            runner=_fake_runner_success,
        )
        self.assertIn("command_id", result.metadata)
        self.assertEqual(result.metadata["command_id"], "get_current_time")
        self.assertIn("display_command", result.metadata)
        self.assertIn("workspace", result.metadata)
        self.assertEqual(result.metadata["workspace"], str(self.workspace))
        self.assertIn("exit_code", result.metadata)
        self.assertIn("duration_ms", result.metadata)
        self.assertIn("stdout", result.metadata)
        self.assertIn("stderr", result.metadata)
        self.assertIn("stdout_truncated", result.metadata)
        self.assertIn("stderr_truncated", result.metadata)
        self.assertIn("timed_out", result.metadata)

    def test_validate_args_rejects_extra_keys_after_registry(self) -> None:
        # The registry validate_args rejects extra keys; run_command calls
        # validate_args first via the tool layer. Here we test directly that
        # the registry block works, and in integration the tool layer will
        # call it before execution.
        validation = self.registry.validate_args(
            {"command_id": "get_current_time", "command": "date"}
        )
        self.assertIsNotNone(validation)
        self.assertEqual(validation.error, "invalid_command_args")
