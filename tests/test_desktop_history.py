import json
import tempfile
import time
import unittest
from pathlib import Path

from min_agent_desktop.activity import ActivityReader
from min_agent_desktop.history import read_history, update_history
from min_agent_desktop.store import ProgressStore


class HistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.store = ProgressStore(self.directory)

    def feed(self, state, name="a", **overrides):
        at = state["started_at"] + 0.001
        return {"thread_id": "thread-one", "calls": [{"id": name, "name": "执行命令",
                "status": "completed", "category": "command", "time": at,
                "parameters": "echo ok", "result": "ok", "duration": 0.1, **overrides}],
                "notes": [{"id": name, "time": at, "kind": "commentary", "text": "工作说明"}]}

    def test_restart_retains_task_history_and_does_not_duplicate_events(self):
        state = self.store.begin("任务一", "开始")
        feed = self.feed(state)
        update_history(self.directory, state, feed)
        update_history(self.directory, state, feed)
        new_store = ProgressStore(self.directory)
        self.assertEqual(state, new_store.read())
        archived = read_history(self.directory)["tasks"][0]
        self.assertEqual(1, len(archived["calls"]))
        self.assertEqual(2, len(archived["steps"]))
        self.assertEqual("command", archived["calls"][0]["category"])
        path = self.directory / "history.json"
        modified = path.stat().st_mtime_ns
        update_history(self.directory, state, feed)
        self.assertEqual(modified, path.stat().st_mtime_ns)
        self.assertEqual(0o600, path.stat().st_mode & 0o777)

    def test_task_switch_excludes_old_calls_and_does_not_mark_old_task_complete(self):
        old = self.store.begin("旧任务", "开始")
        feed = self.feed(old, time=old["started_at"])
        update_history(self.directory, old, feed)
        new = self.store.begin("新任务", "开始", replace=True)
        update_history(self.directory, new, feed)
        tasks = read_history(self.directory)["tasks"]
        self.assertEqual("running", tasks[0]["status"])
        self.assertEqual(1, len(tasks[0]["calls"]))
        self.assertEqual([], tasks[1]["calls"])
        # A call that began in the old task must not migrate when it finishes later.
        update_history(self.directory, new, self.feed(new, started_at=old["started_at"]))
        self.assertEqual([], read_history(self.directory)["tasks"][1]["calls"])

    def test_terminal_task_excludes_later_events_and_cross_thread_mixing(self):
        state = self.store.begin("任务", "开始")
        update_history(self.directory, state, self.feed(state))
        other = {**self.feed(state), "thread_id": "another-thread"}
        with self.assertRaises(ValueError):
            update_history(self.directory, state, other)
        ended = self.store.update(state["task_id"], "succeeded", "完成")
        update_history(self.directory, ended, self.feed(state, "later", time=ended["updated_at"] + 1))
        self.assertEqual(["a"], [x["id"] for x in read_history(self.directory)["tasks"][0]["calls"]])

    def test_limits_and_manual_text_redaction(self):
        for i in range(15):
            state = self.store.begin(f"任务 {i}", "API_KEY=verysecret", replace=True)
            for n in range(35):
                self.store.update(state["task_id"], "running", f"步骤 {n}")
                update_history(self.directory, self.store.read(), self.feed(state, str(n)))
        history = read_history(self.directory)
        self.assertEqual(12, len(history["tasks"]))
        self.assertEqual(30, len(history["tasks"][-1]["steps"]))
        self.assertEqual(20, len(history["tasks"][-1]["calls"]))
        self.assertNotIn("verysecret", json.dumps(history))

    def test_corrupt_history_preserved_instead_of_silent_overwrite(self):
        state = self.store.begin("任务", "开始")
        file = self.directory / "history.json"
        file.write_text("{broken")
        with self.assertRaises(ValueError):
            update_history(self.directory, state)
        self.assertEqual("{broken", file.read_text())

    def test_legacy_state_is_labeled_and_does_not_claim_old_call_history(self):
        state = self.store.begin("旧版任务", "开始")
        state.pop("started_at")
        (self.directory / "history.json").unlink()
        update_history(self.directory, state)
        self.assertTrue(read_history(self.directory)["tasks"][0]["legacy"])
        self.assertEqual([], read_history(self.directory)["tasks"][0]["calls"])

    def test_public_notes_are_bounded_and_private_content_excluded(self):
        reader = ActivityReader("thread-one", 0)
        for i in range(40):
            reader.consume({"timestamp": "2026-11-07T00:00:00Z", "type": "event_msg", "payload": {
                "type": "item_completed", "thread_id": "thread-one", "item": {
                    "type": "AgentMessage", "id": str(i), "phase": "commentary", "content": "工作说明"}}})
        reader.consume({"timestamp": "2026-11-07T00:00:00Z", "type": "event_msg", "payload": {
            "type": "item_completed", "thread_id": "thread-one", "item": {
                "type": "AgentMessage", "id": "private", "phase": "analysis", "content": "PRIVATE"}}})
        self.assertEqual(30, len(reader.snapshot(time.time())["notes"]))
        self.assertNotIn("PRIVATE", json.dumps(reader.snapshot(time.time())))
