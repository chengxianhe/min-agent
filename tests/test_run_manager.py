from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class RunManagerTest(unittest.TestCase):
    def setUp(self) -> None:
        from min_agent.permission_broker import PermissionBroker
        from min_agent.run_manager import RunManager
        from min_agent.session_key_store import SessionKeyStore

        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        (self.workspace / "notes.md").write_text("# Notes\ncontent", encoding="utf-8")
        self.keys = SessionKeyStore()
        self.manager = RunManager(
            self.workspace,
            root / "runs",
            self.keys,
            PermissionBroker(),
            step_delay_seconds=0,
            deepseek_model="custom-model",
            deepseek_base_url="https://example.test/v1",
            model_timeout_seconds=7.5,
            model_max_tokens=321,
        )

    def tearDown(self) -> None:
        self.manager.close()
        self.tmp.cleanup()

    def wait_terminal(self) -> dict:
        for _ in range(100):
            snapshot = self.manager.current_snapshot()
            if snapshot and not snapshot["active"]:
                return snapshot
            time.sleep(0.01)
        self.fail("run did not terminate")

    def test_fake_does_not_need_key_and_terminal_run_allows_next_run(self) -> None:
        first = self.manager.start_run("请读取 notes.md 并总结", "fake")
        self.assertEqual(first["decision_model"], "fake")
        terminal = self.wait_terminal()
        self.assertEqual(terminal["status"], "completed")
        second = self.manager.start_run("请读取 notes.md 并总结", "fake")
        self.assertNotEqual(first["run_id"], second["run_id"])

    def test_deepseek_requires_memory_key_before_worker_creation(self) -> None:
        with self.assertRaises(RuntimeError):
            self.manager.start_run("goal", "deepseek")
        self.assertIsNone(self.manager.current_snapshot())

    def test_non_string_run_fields_are_rejected_before_worker_creation(self) -> None:
        invalid_requests = (
            (123, "fake"),
            ("goal", 123),
        )

        for goal, decision_model in invalid_requests:
            with self.subTest(goal=goal, decision_model=decision_model):
                with self.assertRaises(ValueError):
                    self.manager.start_run(goal, decision_model)
                self.assertIsNone(self.manager.current_snapshot())

    def test_model_factory_receives_configured_runtime_options(self) -> None:
        from min_agent.run_manager import build_web_decision_model

        with patch(
            "min_agent.run_manager.build_web_decision_model",
            wraps=build_web_decision_model,
        ) as build_model:
            self.manager.start_run("请读取 notes.md 并总结", "fake")
            self.wait_terminal()

        build_model.assert_called_once_with(
            "fake",
            api_key=None,
            deepseek_model="custom-model",
            deepseek_base_url="https://example.test/v1",
            model_timeout_seconds=7.5,
            model_max_tokens=321,
        )

    def test_unexpected_runtime_error_is_observable_without_raw_message(self) -> None:
        with patch(
            "min_agent.run_manager.build_web_decision_model",
            side_effect=RuntimeError("sensitive-runtime-details"),
        ):
            self.manager.start_run("请读取 notes.md 并总结", "fake")
            terminal = self.wait_terminal()

        failed_events = [
            event for event in terminal["events"] if event["phase"] == "run_failed"
        ]
        self.assertEqual(terminal["status"], "failed")
        self.assertEqual(terminal["result"]["success"], False)
        self.assertEqual(len(failed_events), 1)
        self.assertEqual(failed_events[0]["output"]["error_type"], "RuntimeError")
        self.assertNotIn("sensitive-runtime-details", json.dumps(terminal))
