from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class CliTest(unittest.TestCase):
    def test_cli_registers_four_tools_including_run_command(self) -> None:
        from min_agent.cli import build_tool_registry

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            registry = build_tool_registry(workspace)

        tool_names = {tool.name for tool in registry.list_specs()}
        self.assertEqual(tool_names, {"read_file", "list_dir", "write_file", "run_command"})

    def test_write_file_spec_requires_permission(self) -> None:
        from min_agent.cli import build_tool_registry

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            registry = build_tool_registry(workspace)

        specs = {spec.name: spec for spec in registry.list_specs()}
        self.assertFalse(specs["read_file"].requires_permission)
        self.assertFalse(specs["list_dir"].requires_permission)
        self.assertTrue(specs["write_file"].requires_permission)
        self.assertTrue(specs["run_command"].requires_permission)

    def test_run_command_schema_is_exact(self) -> None:
        from min_agent.cli import build_tool_registry

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            registry = build_tool_registry(workspace)

        spec = registry.get_spec("run_command")
        self.assertEqual(spec.args_schema, {"command_id": "string"})

    def test_run_command_validator_blocks_unknown_id(self) -> None:
        from min_agent.cli import build_tool_registry

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            registry = build_tool_registry(workspace)

        error = registry.validate_call("run_command", {"command_id": "delete_everything"})
        self.assertIsNotNone(error)
        self.assertEqual(error.error, "unknown_command_id")

    def test_cli_runs_without_viewer_and_saves_record(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()
            (workspace / "notes.md").write_text("# 示例\n这是 demo。", encoding="utf-8")

            exit_code = main(
                [
                    "请读取 notes.md 并总结",
                    "--workspace",
                    str(workspace),
                    "--runs-dir",
                    str(runs),
                    "--no-browser",
                    "--no-viewer",
                    "--step-delay",
                    "0",
                ]
            )

            records = list(runs.glob("*.json"))
            data = json.loads(records[0].read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(data["status"], "completed")

    def test_cli_returns_error_for_missing_workspace(self) -> None:
        from min_agent.cli import main

        exit_code = main(
            [
                "请读取 notes.md 并总结",
                "--workspace",
                "missing-workspace",
                "--no-browser",
                "--no-viewer",
            ]
        )

        self.assertEqual(exit_code, 2)

    def test_cli_returns_error_for_workspace_file(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            workspace_file = Path(tmp) / "workspace.txt"
            workspace_file.write_text("not a directory", encoding="utf-8")

            exit_code = main(
                [
                    "请读取 notes.md 并总结",
                    "--workspace",
                    str(workspace_file),
                    "--no-browser",
                    "--no-viewer",
                ]
            )

        self.assertEqual(exit_code, 2)

    def test_cli_returns_error_when_viewer_cannot_start(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            (workspace / "notes.md").write_text("# 示例", encoding="utf-8")

            with patch("min_agent.cli.TraceServer", side_effect=OSError("bind failed")):
                exit_code = main(
                    [
                        "请读取 notes.md 并总结",
                        "--workspace",
                        str(workspace),
                        "--no-browser",
                    ]
                )

        self.assertEqual(exit_code, 2)

    def test_cli_default_fake_mode_does_not_require_deepseek_key(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()
            (workspace / "notes.md").write_text("# 示例", encoding="utf-8")

            with patch.dict("os.environ", {}, clear=True):
                exit_code = main(
                    [
                        "请读取 notes.md 并总结",
                        "--workspace",
                        str(workspace),
                        "--runs-dir",
                        str(runs),
                        "--no-viewer",
                        "--no-browser",
                        "--step-delay",
                        "0",
                    ]
                )

        self.assertEqual(exit_code, 0)

    def test_cli_deepseek_mode_requires_key(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            (workspace / "notes.md").write_text("# 示例", encoding="utf-8")

            with patch.dict("os.environ", {}, clear=True):
                exit_code = main(
                    [
                        "请读取 notes.md 并总结",
                        "--workspace",
                        str(workspace),
                        "--decision-model",
                        "deepseek",
                        "--no-viewer",
                        "--no-browser",
                    ]
                )

        self.assertEqual(exit_code, 2)


    def test_confirm_tool_call_returns_true_for_y(self) -> None:
        from min_agent.cli import confirm_tool_call
        from min_agent.types import AgentAction

        action = AgentAction.tool_call("write_file", {"path": "summary.md"}, "need to write")
        with patch("builtins.input", return_value="y"):
            result = confirm_tool_call(action, {})

        self.assertTrue(result)

    def test_confirm_tool_call_returns_true_for_uppercase_y(self) -> None:
        from min_agent.cli import confirm_tool_call
        from min_agent.types import AgentAction

        action = AgentAction.tool_call("write_file", {"path": "summary.md"}, "need to write")
        with patch("builtins.input", return_value="Y"):
            result = confirm_tool_call(action, {})

        self.assertTrue(result)

    def test_confirm_tool_call_returns_false_for_empty_input(self) -> None:
        from min_agent.cli import confirm_tool_call
        from min_agent.types import AgentAction

        action = AgentAction.tool_call("write_file", {"path": "summary.md"}, "need to write")
        with patch("builtins.input", return_value=""):
            result = confirm_tool_call(action, {})

        self.assertFalse(result)

    def test_confirm_tool_call_returns_false_for_n(self) -> None:
        from min_agent.cli import confirm_tool_call
        from min_agent.types import AgentAction

        action = AgentAction.tool_call("write_file", {"path": "summary.md"}, "need to write")
        with patch("builtins.input", return_value="n"):
            result = confirm_tool_call(action, {})

        self.assertFalse(result)

    def test_confirm_tool_call_renders_command_details(self) -> None:
        from min_agent.cli import confirm_tool_call
        from min_agent.types import AgentAction
        import io
        import sys as _sys

        action = AgentAction.tool_call(
            "run_command",
            {"command_id": "get_current_time"},
            "need current time",
        )
        details = {
            "command_id": "get_current_time",
            "command": '/bin/date "+%Y-%m-%d %H:%M:%S %Z"',
            "workspace": "/tmp/ws",
            "risk": "该命令只读取本机当前时间，不修改文件、不访问网络。",
        }

        captured = io.StringIO()
        old_stdout = _sys.stdout
        _sys.stdout = captured
        try:
            with patch("builtins.input", return_value="y"):
                result = confirm_tool_call(action, details)
        finally:
            _sys.stdout = old_stdout

        self.assertTrue(result)
        output = captured.getvalue()
        self.assertIn("Permission required: run_command", output)
        self.assertIn("Action: get_current_time", output)
        self.assertIn("Command: /bin/date", output)
        self.assertIn("Risk: 该命令只读取", output)

    def test_preview_text_truncates_content_longer_than_200(self) -> None:
        from min_agent.cli import preview_text

        long_text = "a" * 250
        result = preview_text(long_text)

        self.assertEqual(len(result), 203)
        self.assertTrue(result.endswith("..."))

    def test_preview_text_does_not_truncate_short_content(self) -> None:
        from min_agent.cli import preview_text

        short_text = "a" * 100
        result = preview_text(short_text)

        self.assertEqual(result, short_text)


if __name__ == "__main__":
    unittest.main()
