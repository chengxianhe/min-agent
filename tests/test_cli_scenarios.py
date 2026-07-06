from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def load_single_run_record(runs_dir: Path) -> dict:
    records = list(runs_dir.glob("*.json"))
    if len(records) != 1:
        raise AssertionError(f"expected exactly one run record, got {len(records)}")
    return json.loads(records[0].read_text(encoding="utf-8"))


def phases(record: dict) -> list[str]:
    return [event["phase"] for event in record["events"]]


def tool_started_names(record: dict) -> list[str]:
    return [
        event["input"]["tool_name"]
        for event in record["events"]
        if event["phase"] == "tool_started"
    ]


class CliScenarioTest(unittest.TestCase):
    def test_multi_file_summary_record_shows_discover_read_answer_chain(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()
            (workspace / "project.md").write_text("# 项目\nmin-agent-demo", encoding="utf-8")
            (workspace / "architecture.md").write_text("# 架构\nAgentLoop", encoding="utf-8")

            exit_code = main(
                [
                    "请阅读这个工作区里的资料，并总结这个 demo 是怎么工作的",
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
            record = load_single_run_record(runs)

        self.assertEqual(exit_code, 0)
        self.assertEqual(record["status"], "completed")
        self.assertIn("run_started", phases(record))
        self.assertIn("context_built", phases(record))
        self.assertIn("llm_decision", phases(record))
        self.assertIn("observation_added", phases(record))
        self.assertIn("final_answer", phases(record))
        self.assertIn("run_completed", phases(record))
        self.assertIn("list_dir", tool_started_names(record))
        self.assertIn("read_file", tool_started_names(record))

    def test_approved_write_record_shows_permission_before_write_tool_execution(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()
            (workspace / "project.md").write_text("# 项目\nmin-agent-demo", encoding="utf-8")

            with patch("builtins.input", return_value="y"):
                exit_code = main(
                    [
                        "请阅读这个工作区里的资料，并生成 summary.md",
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
            record = load_single_run_record(runs)
            summary_exists = (workspace / "summary.md").exists()

        event_phases = phases(record)
        write_started_index = next(
            index
            for index, event in enumerate(record["events"])
            if event["phase"] == "tool_started"
            and event["input"]["tool_name"] == "write_file"
        )
        permission_requested_index = event_phases.index("permission_requested")
        permission_resolved_index = event_phases.index("permission_resolved")

        self.assertEqual(exit_code, 0)
        self.assertEqual(record["status"], "completed")
        self.assertTrue(summary_exists)
        self.assertLess(permission_requested_index, permission_resolved_index)
        self.assertLess(permission_resolved_index, write_started_index)
        self.assertTrue(record["events"][permission_resolved_index]["output"]["approved"])

    def test_rejected_write_record_never_starts_write_file_tool(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()
            (workspace / "project.md").write_text("# 项目\nmin-agent-demo", encoding="utf-8")

            with patch("builtins.input", return_value="n"):
                exit_code = main(
                    [
                        "请阅读这个工作区里的资料，并生成 summary.md",
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
            record = load_single_run_record(runs)
            summary_exists = (workspace / "summary.md").exists()

        self.assertEqual(exit_code, 0)
        self.assertEqual(record["status"], "failed")
        self.assertFalse(summary_exists)
        self.assertIn("permission_requested", phases(record))
        self.assertIn("permission_resolved", phases(record))
        self.assertFalse(
            next(
                event
                for event in record["events"]
                if event["phase"] == "permission_resolved"
            )["output"]["approved"]
        )
        self.assertNotIn("write_file", tool_started_names(record))


class CliContextInjectionTest(unittest.TestCase):
    def test_workspace_config_loaded_when_minagent_md_present(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()
            (workspace / "minagent.md").write_text(
                "# workspace rules\n- always read project.md first\n",
                encoding="utf-8",
            )
            (workspace / "project.md").write_text("# Project\ncontent", encoding="utf-8")

            exit_code = main(
                [
                    "请总结 project.md",
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
            record = load_single_run_record(runs)

        self.assertEqual(exit_code, 0)

        context_built_events = [
            e for e in record["events"] if e["phase"] == "context_built"
        ]
        self.assertGreater(len(context_built_events), 0)
        first_context = context_built_events[0]
        ws_config = first_context["output"].get("workspace_config")
        self.assertIsNotNone(ws_config)
        self.assertEqual(ws_config["status"], "loaded")
        self.assertIn("always read project.md", ws_config["content"])

    def test_workspace_config_not_found_when_minagent_md_missing(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()
            (workspace / "notes.md").write_text("# Notes\nsample", encoding="utf-8")

            exit_code = main(
                [
                    "请总结 notes.md",
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
            record = load_single_run_record(runs)

        self.assertEqual(exit_code, 0)
        self.assertEqual(record["status"], "completed")

        context_built_events = [
            e for e in record["events"] if e["phase"] == "context_built"
        ]
        self.assertGreater(len(context_built_events), 0)
        ws_config = context_built_events[0]["output"].get("workspace_config")
        self.assertIsNotNone(ws_config)
        self.assertEqual(ws_config["status"], "not_found")

    def test_run_memory_loads_same_workspace_history(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()
            runs.mkdir()
            (workspace / "project.md").write_text("# Project\ncontent", encoding="utf-8")

            import json as _json
            pre_record = {
                "run_id": "prev-run",
                "workspace": str(workspace.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "user_goal": "previous goal",
                "status": "completed",
                "events": [
                    {"phase": "tool_started", "input": {"tool_name": "read_file"}},
                    {"phase": "tool_finished", "output": {"success": True}},
                    {"phase": "final_answer", "output": {"message": "previous answer"}},
                ],
            }
            (runs / "prev-run.json").write_text(
                _json.dumps(pre_record, ensure_ascii=False), encoding="utf-8"
            )

            exit_code = main(
                [
                    "请总结 project.md",
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
            records = list(runs.glob("*.json"))
            # Filter out the pre-populated record
            new_records = [
                r for r in records if r.name != "prev-run.json"
            ]
            self.assertEqual(len(new_records), 1)
            record = json.loads(new_records[0].read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)

        context_built_events = [
            e for e in record["events"] if e["phase"] == "context_built"
        ]
        self.assertGreater(len(context_built_events), 0)
        run_memory = context_built_events[0]["output"].get("run_memory")
        self.assertIsNotNone(run_memory)
        self.assertEqual(run_memory["status"], "loaded")
        self.assertGreaterEqual(run_memory["summary_count"], 1)

    # ---- V0.7: command execution scenarios ----

    def test_approved_time_scenario_produces_correct_event_chain(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()

            fake_time = "2026-07-03 10:30:21 CST"
            fake_result = subprocess.CompletedProcess(
                args=["/bin/date", "+%Y-%m-%d %H:%M:%S %Z"],
                returncode=0,
                stdout=fake_time + "\n",
                stderr="",
            )

            with patch("builtins.input", return_value="y"), \
                 patch("subprocess.run", return_value=fake_result):
                exit_code = main(
                    [
                        "现在几点？",
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
            record = load_single_run_record(runs)

        event_phases = phases(record)
        self.assertEqual(exit_code, 0)
        self.assertEqual(record["status"], "completed")

        # Verify ordered subsequence
        self.assertIn("context_built", event_phases)
        self.assertIn("llm_decision", event_phases)
        self.assertIn("permission_requested", event_phases)
        self.assertIn("permission_resolved", event_phases)
        self.assertIn("tool_started", event_phases)
        self.assertIn("tool_finished", event_phases)
        self.assertIn("observation_added", event_phases)
        self.assertIn("final_answer", event_phases)

        # Check order: permission_requested before permission_resolved before tool_started
        req_idx = event_phases.index("permission_requested")
        res_idx = event_phases.index("permission_resolved")
        start_idx = next(
            i for i, e in enumerate(record["events"])
            if e["phase"] == "tool_started" and e["input"].get("tool_name") == "run_command"
        )
        self.assertLess(req_idx, res_idx)
        self.assertLess(res_idx, start_idx)

        # Permission details present
        perm_req = record["events"][req_idx]
        details = perm_req["input"].get("details", {})
        self.assertIn("command", details)

        # Tool finished has exit_code 0
        tool_finished = [
            e for e in record["events"]
            if e["phase"] == "tool_finished" and e["output"]["metadata"].get("command_id") == "get_current_time"
        ]
        self.assertEqual(len(tool_finished), 1)
        self.assertEqual(tool_finished[0]["output"]["metadata"]["exit_code"], 0)

        # Final answer contains the fake time
        final_answer_events = [
            e for e in record["events"] if e["phase"] == "final_answer"
        ]
        self.assertIn(fake_time, final_answer_events[0]["output"]["message"])

        # Two context_built events; second contains the command result in observations
        context_events = [e for e in record["events"] if e["phase"] == "context_built"]
        self.assertEqual(len(context_events), 2)
        observations = context_events[1]["output"]["observations"]
        self.assertTrue(any(
            obs["tool_name"] == "run_command"
            and obs["result"]["content"] == fake_time
            for obs in observations
        ))

    def test_rejected_time_scenario_never_starts_command(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()

            with patch("builtins.input", return_value="n"):
                exit_code = main(
                    [
                        "现在几点？",
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
            record = load_single_run_record(runs)

        self.assertEqual(exit_code, 0)
        self.assertEqual(record["status"], "failed")

        event_phases = phases(record)
        self.assertIn("permission_requested", event_phases)
        self.assertIn("permission_resolved", event_phases)

        # approved is False
        resolved = [
            e for e in record["events"] if e["phase"] == "permission_resolved"
        ]
        self.assertFalse(resolved[0]["output"]["approved"])

        # No tool_started for run_command
        run_command_starts = [
            e for e in record["events"]
            if e["phase"] == "tool_started" and e["input"].get("tool_name") == "run_command"
        ]
        self.assertEqual(run_command_starts, [])

    def test_unknown_command_id_scenario_finishes_without_crash(self) -> None:
        from min_agent.cli import main
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentAction, AgentContext

        class BadCommandModel(FakeLLM):
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "run_command",
                        {"command_id": "delete_everything"},
                        "need to delete",
                    )
                return AgentAction.final_answer("failed", "bad command", success=False)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()

            with patch("min_agent.cli.FakeLLM", return_value=BadCommandModel()):
                exit_code = main(
                    [
                        "现在几点？",
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
            record = load_single_run_record(runs)

        self.assertEqual(exit_code, 0)
        # Should fail gracefully
        self.assertNotIn("tool_started", phases(record))
        self.assertIn("observation_added", phases(record))

    def test_command_timeout_scenario_finishes_without_crash(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()

            with patch("builtins.input", return_value="y"), \
                 patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["/bin/date"], timeout=5.0)):
                exit_code = main(
                    [
                        "现在几点？",
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
            record = load_single_run_record(runs)

        self.assertEqual(exit_code, 0)
        # Should have tool_started and tool_finished with failure
        tool_finished = [
            e for e in record["events"] if e["phase"] == "tool_finished"
        ]
        self.assertEqual(len(tool_finished), 1)
        self.assertTrue(tool_finished[0]["output"]["metadata"]["timed_out"])

    def test_write_file_permission_still_required(self) -> None:
        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            runs = root / "runs"
            workspace.mkdir()
            (workspace / "notes.md").write_text("# Notes\ncontent", encoding="utf-8")

            with patch("builtins.input", return_value="y"):
                exit_code = main(
                    [
                        "读取 notes.md 并生成 output.md",
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
            record = load_single_run_record(runs)

        self.assertEqual(exit_code, 0)

        event_phases = phases(record)
        self.assertIn("permission_requested", event_phases)
        self.assertIn("permission_resolved", event_phases)
        self.assertIn("write_file", tool_started_names(record))


if __name__ == "__main__":
    unittest.main()
