import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from min_agent_desktop.store import ProgressStore


class DesktopCardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = ProgressStore(Path(self.directory.name))

    def test_task_lifecycle_and_terminal_guard(self):
        state = self.store.begin("真实任务", "读取配置")
        task = state["task_id"]
        self.store.update(task, "waiting", "等待确认")
        self.store.update(task, "running", "运行检查")
        self.store.update(task, "succeeded", "自动检查通过", "待人工审查")
        self.assertEqual("succeeded", self.store.read()["status"])
        with self.assertRaises(ValueError):
            self.store.update(task, "running", "错误复活")

    def test_new_task_does_not_silently_replace_active_task(self):
        old = self.store.begin("旧任务", "执行中")
        with self.assertRaises(ValueError):
            self.store.begin("新任务", "开始")
        new = self.store.begin("新任务", "开始", replace=True)
        with self.assertRaises(ValueError):
            self.store.update(old["task_id"], "succeeded", "旧任务完成")
        self.assertEqual(new, self.store.read())

    def test_history_is_bounded_and_private(self):
        task = self.store.begin("任务", "开始")["task_id"]
        for index in range(20):
            self.store.update(task, "running", f"步骤 {index}")
        state = self.store.read()
        self.assertEqual(8, len(state["events"]))
        self.assertEqual("步骤 19", state["events"][-1]["action"])
        self.assertEqual(0o600, self.store.path.stat().st_mode & 0o777)
        self.assertFalse(list(self.store.directory.glob(".state-*")))

    def test_bad_input_preserves_last_valid_state(self):
        original = self.store.begin("任务", "开始")
        for status, action, detail in [("bogus", "动作", ""), ("running", "", ""),
                                       ("running", "x" * 161, ""), ("running", "动作", "x" * 1001)]:
            with self.assertRaises(ValueError):
                self.store.update(original["task_id"], status, action, detail)
            self.assertEqual(original, self.store.read())

    def test_concurrent_updates_do_not_lose_events_or_expose_partial_json(self):
        task = self.store.begin("并发任务", "开始")["task_id"]
        errors = []
        def update(index):
            try:
                ProgressStore(self.store.directory).update(task, "running", f"动作 {index}")
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=update, args=(index,)) for index in range(6)]
        for thread in threads:
            thread.start()
        while any(thread.is_alive() for thread in threads):
            self.assertEqual(task, self.store.read()["task_id"])
        for thread in threads:
            thread.join()
        self.assertEqual([], errors)
        self.assertEqual(7, len(self.store.read()["events"]))

    def test_missing_corrupt_and_oversized_files(self):
        self.assertIsNone(self.store.read())
        for raw in ["{broken", "[]", '{"version":2}', "x" * 65537]:
            self.store.path.write_text(raw)
            with self.assertRaises(ValueError):
                self.store.read()

    def test_real_cli_round_trip(self):
        root = Path(__file__).resolve().parents[1]
        env = {**os.environ, "PYTHONPATH": str(root / "src")}
        command = [sys.executable, "-m", "min_agent_desktop", "--state-dir", self.directory.name]
        first = subprocess.run(command + ["begin", "--title", "CLI 任务", "--action", "检查"],
                               env=env, capture_output=True, text=True, check=True)
        task = json.loads(first.stdout)["task_id"]
        result = subprocess.run(command + ["update", "--task-id", task, "--status", "failed",
                                            "--action", "测试失败", "--detail", "保留失败证据"],
                                env=env, capture_output=True, text=True, check=True)
        self.assertEqual("failed", json.loads(result.stdout)["status"])
        rejected = subprocess.run(command + ["update", "--task-id", task, "--status", "running",
                                              "--action", "重跑"], env=env, capture_output=True, text=True)
        self.assertEqual(1, rejected.returncode)


if __name__ == "__main__":
    unittest.main()
