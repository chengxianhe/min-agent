from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class ContextLoaderWorkspaceConfigTest(unittest.TestCase):
    def test_load_minagent_md_exists(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "minagent.md").write_text("- rule 1\n- rule 2\n", encoding="utf-8")

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(tmp), decision_model="fake")
            config = loader.load_workspace_config()

        self.assertEqual(config.status, "loaded")
        self.assertEqual(config.path, "minagent.md")
        self.assertEqual(config.content, "- rule 1\n- rule 2\n")
        self.assertFalse(config.truncated)
        self.assertTrue(config.preview.startswith("- rule 1"))

    def test_load_minagent_md_not_exists(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            loader = ContextLoader(workspace=str(workspace), runs_dir=str(tmp), decision_model="fake")
            config = loader.load_workspace_config()

        self.assertEqual(config.status, "not_found")
        self.assertEqual(config.content, "")

    def test_load_minagent_md_rejects_external_symlink(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            outside = Path(tmp) / "outside.md"
            outside.write_text("external content", encoding="utf-8")

            symlink = workspace / "minagent.md"
            symlink.symlink_to(outside.resolve())

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(tmp), decision_model="fake")
            config = loader.load_workspace_config()

        self.assertEqual(config.status, "error")
        self.assertIn("symlink", config.error)

    def test_load_minagent_md_invalid_utf8_returns_error(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "minagent.md").write_bytes(b"\xff\xfe\x00\x00")

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(tmp), decision_model="fake")
            config = loader.load_workspace_config()

        self.assertEqual(config.status, "error")
        self.assertIn("utf8", config.error)

    def test_load_minagent_md_truncates_at_8000_chars(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            long_content = "x" * 8100
            (workspace / "minagent.md").write_text(long_content, encoding="utf-8")

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(tmp), decision_model="fake")
            config = loader.load_workspace_config()

        self.assertEqual(config.status, "loaded")
        self.assertEqual(len(config.content), 8000)
        self.assertTrue(config.truncated)
        self.assertEqual(len(config.preview), 200)


class ContextLoaderRunMemoryTest(unittest.TestCase):
    def _write_record(self, runs_dir: Path, record: dict) -> Path:
        path = runs_dir / f"{record['run_id']}.json"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return path

    def test_load_run_memory_with_valid_records(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            for i in range(3):
                self._write_record(runs_dir, {
                    "run_id": f"run-{i}",
                    "workspace": str(workspace.resolve()),
                    "started_at": f"2026-06-30T10:00:0{i}+08:00",
                    "user_goal": f"goal {i}",
                    "status": "completed",
                    "events": [
                        {"phase": "tool_started", "input": {"tool_name": "read_file"}},
                        {"phase": "tool_finished", "output": {"success": True}},
                        {"phase": "final_answer", "output": {"message": f"answer {i}"}},
                    ],
                })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        self.assertEqual(memory.status, "loaded")
        self.assertEqual(memory.summary_count, 3)
        self.assertEqual(len(memory.summaries), 3)

    def test_load_run_memory_empty_dir(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        self.assertEqual(memory.status, "empty")
        self.assertEqual(memory.summary_count, 0)

    def test_load_run_memory_skips_corrupted(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            # corrupted JSON
            (runs_dir / "bad.json").write_text("{not json", encoding="utf-8")

            # valid record
            self._write_record(runs_dir, {
                "run_id": "good-run",
                "workspace": str(workspace.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "user_goal": "valid goal",
                "status": "completed",
                "events": [{"phase": "final_answer", "output": {"message": "ok"}}],
            })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        self.assertEqual(memory.status, "loaded")
        self.assertEqual(memory.summary_count, 1)

    def test_load_run_memory_skips_missing_fields(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            self._write_record(runs_dir, {
                "run_id": "no-goal",
                # missing user_goal
                "workspace": str(workspace.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "status": "completed",
                "events": [],
            })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        self.assertEqual(memory.status, "empty")

    def test_load_run_memory_excludes_other_workspaces(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            other_ws = temp_dir / "other_ws"
            other_ws.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            self._write_record(runs_dir, {
                "run_id": "other-run",
                "workspace": str(other_ws.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "user_goal": "other goal",
                "status": "completed",
                "events": [],
            })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        self.assertEqual(memory.status, "empty")

    def test_load_run_memory_collects_three_valid_records_after_skips(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            # 5 valid records, should only take 3 most recent
            for i in range(5):
                self._write_record(runs_dir, {
                    "run_id": f"run-{i}",
                    "workspace": str(workspace.resolve()),
                    "started_at": f"2026-06-30T10:00:{i:02d}+08:00",
                    "user_goal": f"goal {i}",
                    "status": "completed",
                    "events": [{"phase": "final_answer", "output": {"message": f"answer {i}"}}],
                })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory(max_count=3)

        self.assertEqual(memory.status, "loaded")
        self.assertEqual(memory.summary_count, 3)
        # should be the 3 most recent (started_at descending: 04, 03, 02)
        summary_ids = [s.run_id for s in memory.summaries]
        self.assertEqual(summary_ids, ["run-4", "run-3", "run-2"])

    def test_created_file_path_requires_successful_write(self) -> None:
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            # write_file that failed - should NOT produce created_file_path
            self._write_record(runs_dir, {
                "run_id": "failed-write",
                "workspace": str(workspace.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "user_goal": "write test",
                "status": "failed",
                "events": [
                    {"phase": "tool_started", "input": {"tool_name": "write_file", "args": {"path": "out.md"}}},
                    {"phase": "tool_finished", "output": {"success": False, "metadata": {"path": "out.md"}}},
                ],
            })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        self.assertEqual(memory.status, "loaded")
        self.assertEqual(memory.summaries[0].created_file_path, "")


class ContextLoaderToolCatalogTest(unittest.TestCase):
    def test_build_tool_catalog_includes_permission(self) -> None:
        from min_agent.context_loader import ContextLoader
        from min_agent.types import ToolSpec

        tools = [
            ToolSpec(name="write_file", description="Write file", requires_permission=True),
        ]
        loader = ContextLoader(workspace="ws", runs_dir="runs", decision_model="fake")
        catalog = loader.build_tool_catalog(tools)

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0].name, "write_file")
        self.assertTrue(catalog[0].requires_permission)

    def test_build_tool_catalog_readonly_tools(self) -> None:
        from min_agent.context_loader import ContextLoader
        from min_agent.types import ToolSpec

        tools = [
            ToolSpec(name="list_dir", description="List dir", requires_permission=False),
            ToolSpec(name="read_file", description="Read file", requires_permission=False),
        ]
        loader = ContextLoader(workspace="ws", runs_dir="runs", decision_model="fake")
        catalog = loader.build_tool_catalog(tools)

        self.assertEqual(len(catalog), 2)
        self.assertFalse(catalog[0].requires_permission)
        self.assertFalse(catalog[1].requires_permission)

    def test_build_tool_catalog_includes_run_command_with_schema(self) -> None:
        from min_agent.context_loader import ContextLoader
        from min_agent.types import ToolSpec

        tools = [
            ToolSpec(
                name="run_command",
                description="Run one predefined local command action after approval.",
                args_schema={"command_id": "string"},
                requires_permission=True,
            ),
        ]
        loader = ContextLoader(workspace="ws", runs_dir="runs", decision_model="fake")
        catalog = loader.build_tool_catalog(tools)

        self.assertEqual(len(catalog), 1)
        entry = catalog[0]
        self.assertEqual(entry.name, "run_command")
        self.assertTrue(entry.requires_permission)
        self.assertEqual(entry.args_schema, {"command_id": "string"})

    def test_build_tool_catalog_empty_args_schema_defaults_to_empty_dict(self) -> None:
        from min_agent.context_loader import ContextLoader
        from min_agent.types import ToolSpec

        tools = [
            ToolSpec(name="read_file", description="Read file", requires_permission=False),
        ]
        loader = ContextLoader(workspace="ws", runs_dir="runs", decision_model="fake")
        catalog = loader.build_tool_catalog(tools)

        self.assertEqual(catalog[0].args_schema, {})

    def test_build_tool_catalog_run_command_requires_permission(self) -> None:
        from min_agent.context_loader import ContextLoader
        from min_agent.types import ToolSpec

        tools = [
            ToolSpec(
                name="run_command",
                description="Run one predefined local command action after approval.",
                args_schema={"command_id": "string"},
                requires_permission=True,
            ),
        ]
        loader = ContextLoader(workspace="ws", runs_dir="runs", decision_model="fake")
        catalog = loader.build_tool_catalog(tools)

        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0].name, "run_command")
        self.assertTrue(catalog[0].requires_permission)


class ContextLoaderMalformedRecordsTest(unittest.TestCase):
    """回归：畸形 run record 不应导致崩溃。"""

    def _write_record(self, runs_dir: Path, record: dict) -> Path:
        path = runs_dir / f"{record.get('run_id', 'unknown')}.json"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        return path

    def test_events_containing_null_elements_are_skipped(self) -> None:
        """events: [null] — 逐个元素不是 dict，应被跳过。"""
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            self._write_record(runs_dir, {
                "run_id": "null-events",
                "workspace": str(workspace.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "user_goal": "goal",
                "status": "completed",
                "events": [None],
            })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        self.assertEqual(memory.status, "empty")

    def test_events_containing_int_elements_are_skipped(self) -> None:
        """events: [42] — 不是 dict，应被跳过。"""
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            self._write_record(runs_dir, {
                "run_id": "int-events",
                "workspace": str(workspace.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "user_goal": "goal",
                "status": "completed",
                "events": [42],
            })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        self.assertEqual(memory.status, "empty")

    def test_events_containing_empty_list_elements_are_skipped(self) -> None:
        """events: [[]] — 不是 dict，应被跳过。"""
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            self._write_record(runs_dir, {
                "run_id": "list-events",
                "workspace": str(workspace.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "user_goal": "goal",
                "status": "completed",
                "events": [[]],
            })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        self.assertEqual(memory.status, "empty")

    def test_event_output_null_does_not_crash(self) -> None:
        """event output 为 null 时不应触发 AttributeError。"""
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            self._write_record(runs_dir, {
                "run_id": "null-output",
                "workspace": str(workspace.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "user_goal": "goal",
                "status": "completed",
                "events": [
                    {"phase": "final_answer", "output": None},
                ],
            })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        # 不应崩溃，final_answer_preview 应为空
        self.assertEqual(memory.status, "loaded")
        self.assertEqual(memory.summaries[0].final_answer_preview, "")

    def test_event_input_null_does_not_crash(self) -> None:
        """event input 为 null 时不应触发 AttributeError。"""
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            self._write_record(runs_dir, {
                "run_id": "null-input",
                "workspace": str(workspace.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "user_goal": "goal",
                "status": "completed",
                "events": [
                    {"phase": "tool_started", "input": None},
                    {"phase": "tool_finished", "output": {"success": True}},
                ],
            })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        # 不应崩溃，key_tool_chain 为空
        self.assertEqual(memory.status, "loaded")
        self.assertEqual(memory.summaries[0].key_tool_chain, [])

    def test_mixed_valid_and_invalid_event_elements(self) -> None:
        """混合有效和无效 event 元素 — 整条记录被安全跳过，不崩溃。"""
        from min_agent.context_loader import ContextLoader

        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp)
            workspace = temp_dir / "ws"
            workspace.mkdir()
            runs_dir = temp_dir / "runs"
            runs_dir.mkdir()

            self._write_record(runs_dir, {
                "run_id": "mixed-events",
                "workspace": str(workspace.resolve()),
                "started_at": "2026-06-30T10:00:00+08:00",
                "user_goal": "goal",
                "status": "completed",
                "events": [
                    None,
                    42,
                    [],
                    {"phase": "tool_started", "input": {"tool_name": "read_file"}},
                    {"phase": "tool_finished", "output": {"success": True}},
                    {"phase": "final_answer", "output": {"message": "ok"}},
                ],
            })

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            memory = loader.load_run_memory()

        # events 数组包含非 dict 元素，整条记录被安全跳过
        self.assertEqual(memory.status, "empty")


if __name__ == "__main__":
    unittest.main()
