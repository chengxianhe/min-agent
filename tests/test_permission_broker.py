from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class PermissionBrokerTest(unittest.TestCase):
    def test_approval_unblocks_exactly_once(self) -> None:
        from min_agent.permission_broker import PermissionAlreadyResolved, PermissionBroker
        from min_agent.types import AgentAction

        broker = PermissionBroker()
        started = threading.Event()
        result: list[bool] = []

        def request() -> None:
            started.set()
            result.append(
                broker.request(
                    "run",
                    AgentAction.tool_call(
                        "write_file",
                        {"path": "a.md", "content": "x", "mode": "create"},
                        "write",
                    ),
                    {},
                )
            )

        worker = threading.Thread(target=request)
        worker.start()
        self.assertTrue(started.wait(1))

        snapshot = None
        for _ in range(100):
            snapshot = broker.current()
            if snapshot:
                break
            time.sleep(0.01)
        self.assertIsNotNone(snapshot)
        assert snapshot is not None

        resolved = broker.resolve(snapshot.permission_id, True)
        worker.join(1)

        self.assertEqual(resolved.status, "approved")
        self.assertEqual(result, [True])
        with self.assertRaises(PermissionAlreadyResolved):
            broker.resolve(snapshot.permission_id, True)

    def test_resolved_permission_remains_already_resolved_after_next_request(self) -> None:
        from min_agent.permission_broker import (
            PermissionAlreadyResolved,
            PermissionBroker,
            PermissionNotFound,
        )
        from min_agent.types import AgentAction

        broker = PermissionBroker()
        results: list[bool] = []

        def request(path: str) -> None:
            results.append(
                broker.request(
                    "run",
                    AgentAction.tool_call(
                        "write_file",
                        {"path": path, "content": "x", "mode": "create"},
                        "write",
                    ),
                    {},
                )
            )

        first_worker = threading.Thread(target=request, args=("first.md",))
        first_worker.start()
        first = self._wait_for_permission(broker)
        broker.resolve(first.permission_id, True)
        first_worker.join(1)

        second_worker = threading.Thread(target=request, args=("second.md",))
        second_worker.start()
        second = self._wait_for_permission(broker, excluding=first.permission_id)

        try:
            with self.assertRaises(PermissionAlreadyResolved):
                broker.resolve(first.permission_id, True)
            with self.assertRaises(PermissionNotFound):
                broker.resolve("unknown-permission", True)
        finally:
            broker.resolve(second.permission_id, False)
            second_worker.join(1)

        self.assertFalse(first_worker.is_alive())
        self.assertFalse(second_worker.is_alive())
        self.assertEqual(results, [True, False])

    @staticmethod
    def _wait_for_permission(broker, excluding: str | None = None):
        for _ in range(100):
            snapshot = broker.current()
            if snapshot and snapshot.status == "pending" and snapshot.permission_id != excluding:
                return snapshot
            time.sleep(0.01)
        raise AssertionError("permission was not published")
