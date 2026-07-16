from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class WebServerTest(unittest.TestCase):
    def setUp(self) -> None:
        from min_agent.permission_broker import PermissionBroker
        from min_agent.run_history import RunHistory
        from min_agent.run_manager import RunManager
        from min_agent.session_key_store import SessionKeyStore
        from min_agent.web_server import WebAgentServer

        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        workspace = root / "workspace"
        workspace.mkdir()
        self.keys = SessionKeyStore()
        self.manager = RunManager(
            workspace,
            root / "runs",
            self.keys,
            PermissionBroker(),
            step_delay_seconds=0,
        )
        self.server = WebAgentServer(
            self.manager,
            RunHistory(root / "runs"),
            self.keys,
            ROOT / "web",
            0,
        )
        self.server.start()

    def tearDown(self) -> None:
        self.server.close()
        self.manager.close()
        self.tmp.cleanup()

    def call(
        self,
        path: str,
        method: str = "GET",
        body: object | None = None,
        origin: bool = True,
    ) -> tuple[int, dict | bytes]:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Host": self.server.origin.removeprefix("http://")}
        if origin:
            headers["Origin"] = self.server.origin
        if data is not None:
            headers["Content-Type"] = "application/json"

        request = Request(
            self.server.origin + path,
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request) as response:
                raw = response.read()
                if "application/json" in response.headers["Content-Type"]:
                    return response.status, json.loads(raw)
                return response.status, raw
        except HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_state_and_static_page_are_same_origin_loopback_only(self) -> None:
        status, page = self.call("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Min Agent", page)

        status, response = self.call("/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(response["ok"])
        self.assertEqual(response["data"]["service_state"], "ready")

    def test_mutation_requires_origin_and_rejects_extra_workspace(self) -> None:
        status, response = self.call(
            "/api/runs",
            "POST",
            {"goal": "x", "decision_model": "fake"},
            origin=False,
        )
        self.assertEqual(status, 403)
        self.assertEqual(response["error"]["code"], "invalid_origin")

        status, response = self.call(
            "/api/runs",
            "POST",
            {
                "goal": "x",
                "decision_model": "fake",
                "workspace": "/tmp",
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "invalid_request")

    def test_key_response_never_echoes_input(self) -> None:
        sentinel = "web-server-test-key-not-real"
        status, response = self.call(
            "/api/deepseek-key",
            "PUT",
            {"api_key": sentinel},
        )
        self.assertEqual(status, 200)
        self.assertEqual(response["data"], {"configured": True})
        self.assertNotIn(sentinel, json.dumps(response))

    def test_non_string_key_is_rejected_as_invalid_input(self) -> None:
        status, response = self.call(
            "/api/deepseek-key",
            "PUT",
            {"api_key": 123},
        )

        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "invalid_key")
        self.assertFalse(self.keys.is_configured())

    def test_non_string_goal_is_rejected_as_invalid_input(self) -> None:
        status, response = self.call(
            "/api/runs",
            "POST",
            {"goal": 123, "decision_model": "fake"},
        )

        self.assertEqual(status, 400)
        self.assertEqual(response["error"]["code"], "invalid_request")
        self.assertIsNone(self.manager.current_snapshot())

    def test_key_mutation_is_rejected_while_deepseek_run_is_active(self) -> None:
        self.keys.configure("test-key")

        class ActiveDeepSeekManager:
            def has_active_deepseek_run(self) -> bool:
                return True

        original = self.server.manager
        self.server.manager = ActiveDeepSeekManager()
        try:
            status, response = self.call(
                "/api/deepseek-key",
                "PUT",
                {"api_key": "replacement"},
            )
            self.assertEqual(status, 409)
            self.assertEqual(response["error"]["code"], "active_deepseek_run")
        finally:
            self.server.manager = original
