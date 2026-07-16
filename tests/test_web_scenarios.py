from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class WebScenarioTest(unittest.TestCase):
    def setUp(self) -> None:
        from min_agent.permission_broker import PermissionBroker
        from min_agent.run_history import RunHistory
        from min_agent.run_manager import RunManager
        from min_agent.session_key_store import SessionKeyStore
        from min_agent.web_server import WebAgentServer

        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.workspace = root / "workspace"
        self.workspace.mkdir()
        (self.workspace / "project.md").write_text("# Project\ncontent", encoding="utf-8")
        (self.workspace / "architecture.md").write_text("# Architecture\ncontent", encoding="utf-8")
        self.keys = SessionKeyStore()
        self.manager = RunManager(self.workspace, root / "runs", self.keys, PermissionBroker(), step_delay_seconds=0)
        self.server = WebAgentServer(self.manager, RunHistory(root / "runs"), self.keys, ROOT / "web", 0)
        self.server.start()

    def tearDown(self) -> None:
        self.server.close()
        self.manager.close()
        self.tmp.cleanup()

    def request(self, path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Host": self.server.origin.removeprefix("http://"), "Origin": self.server.origin}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.server.origin + path, data=payload, headers=headers, method=method)
        try:
            with urlopen(request) as response:
                return response.status, json.loads(response.read())
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def wait_for_permission(self) -> dict:
        for _ in range(100):
            _, response = self.request("/api/permissions/current")
            if response["data"] is not None:
                return response["data"]
            time.sleep(0.01)
        self.fail("permission was not published")

    def wait_for_terminal(self) -> dict:
        for _ in range(100):
            _, response = self.request("/api/runs/current")
            if response["data"] and not response["data"]["active"]:
                return response["data"]
            time.sleep(0.01)
        self.fail("run did not finish")

    def test_fake_simple_run_uses_real_agent_loop_and_saved_history(self) -> None:
        status, response = self.request("/api/runs", "POST", {"goal": "请读取 project.md 并总结", "decision_model": "fake"})
        self.assertEqual(status, 201)
        terminal = self.wait_for_terminal()
        phases = [event["phase"] for event in terminal["events"]]
        self.assertEqual(terminal["status"], "completed")
        self.assertIn("tool_started", phases)
        self.assertIn("final_answer", phases)
        _, history = self.request("/api/history")
        self.assertEqual(history["data"]["runs"][0]["run_id"], response["data"]["run_id"])

    def test_web_approval_chain_executes_each_dangerous_tool_once(self) -> None:
        status, _ = self.request("/api/runs", "POST", {"goal": "阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。", "decision_model": "fake"})
        self.assertEqual(status, 201)
        first = self.wait_for_permission()
        self.assertEqual(first["tool_name"], "run_command")
        self.assertEqual(self.request(f"/api/permissions/{first['permission_id']}/decision", "POST", {"approved": True})[0], 200)
        self.assertEqual(self.request(f"/api/permissions/{first['permission_id']}/decision", "POST", {"approved": True})[0], 409)
        second = self.wait_for_permission()
        self.assertEqual(second["tool_name"], "write_file")
        self.assertEqual(self.request(f"/api/permissions/{second['permission_id']}/decision", "POST", {"approved": True})[0], 200)
        terminal = self.wait_for_terminal()
        names = [event["input"].get("tool_name") for event in terminal["events"] if event["phase"] == "tool_started"]
        self.assertEqual(names.count("run_command"), 1)
        self.assertEqual(names.count("write_file"), 1)
        self.assertTrue((self.workspace / "summary.md").exists())

    def test_rejection_never_starts_the_rejected_tool(self) -> None:
        self.request("/api/runs", "POST", {"goal": "阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。", "decision_model": "fake"})
        pending = self.wait_for_permission()
        self.assertEqual(self.request(f"/api/permissions/{pending['permission_id']}/decision", "POST", {"approved": False})[0], 200)
        terminal = self.wait_for_terminal()
        names = [event["input"].get("tool_name") for event in terminal["events"] if event["phase"] == "tool_started"]
        self.assertNotIn("run_command", names)
        self.assertFalse((self.workspace / "summary.md").exists())

    def test_history_is_read_only_and_orders_terminal_records(self) -> None:
        _, first = self.request("/api/runs", "POST", {"goal": "请读取 project.md 并总结", "decision_model": "fake"})
        self.wait_for_terminal()
        _, second = self.request("/api/runs", "POST", {"goal": "请读取 architecture.md 并总结", "decision_model": "fake"})
        self.wait_for_terminal()
        _, history = self.request("/api/history")
        rows = history["data"]["runs"]
        self.assertEqual(
            [row["run_id"] for row in rows],
            sorted([first["data"]["run_id"], second["data"]["run_id"]], reverse=True),
        )
        _, record = self.request("/api/history/" + first["data"]["run_id"])
        self.assertEqual(record["data"]["run_id"], first["data"]["run_id"])
        self.assertFalse(any(event["phase"] == "permission_requested" for event in record["data"]["events"]))
