from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TraceRecorderTest(unittest.TestCase):
    def test_emit_increments_steps_and_notifies_subscribers(self) -> None:
        from min_agent.trace_recorder import TraceRecorder

        received = []
        recorder = TraceRecorder(user_goal="goal", workspace="workspace")
        recorder.subscribe(received.append)

        event = recorder.emit(
            phase="run_started",
            status="running",
            title="收到任务",
            reason="用户提交任务",
        )

        self.assertEqual(event.step, 1)
        self.assertEqual(received[0], event)

    def test_save_writes_json_run_record(self) -> None:
        from min_agent.trace_recorder import TraceRecorder

        with tempfile.TemporaryDirectory() as tmp:
            recorder = TraceRecorder(user_goal="goal", workspace="workspace")
            recorder.emit("run_started", "running", "收到任务")
            path = recorder.save(Path(tmp), status="completed")

            data = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["user_goal"], "goal")
        self.assertEqual(len(data["events"]), 1)


if __name__ == "__main__":
    unittest.main()


# ===== V0.8 新增测试 =====


class TraceRecorderV08Test(unittest.TestCase):
    def test_emit_with_task_id(self) -> None:
        from min_agent.trace_recorder import TraceRecorder

        received = []
        recorder = TraceRecorder(user_goal="goal", workspace="workspace")
        recorder.subscribe(received.append)

        event = recorder.emit(
            phase="task_started",
            status="running",
            title="开始任务",
            task_id="task-1",
        )

        self.assertEqual(event.task_id, "task-1")
        self.assertEqual(received[0].task_id, "task-1")

    def test_emit_without_task_id_defaults_to_none(self) -> None:
        from min_agent.trace_recorder import TraceRecorder

        event = TraceRecorder(user_goal="goal", workspace="workspace").emit(
            phase="tool_started",
            status="running",
            title="调用工具",
        )

        self.assertIsNone(event.task_id)

    def test_save_preserves_task_id(self) -> None:
        import json
        import tempfile
        from pathlib import Path

        from min_agent.trace_recorder import TraceRecorder

        with tempfile.TemporaryDirectory() as tmp:
            recorder = TraceRecorder(user_goal="goal", workspace="workspace")
            recorder.emit("task_started", "running", "开始", task_id="task-1")
            path = recorder.save(Path(tmp), status="completed")

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["events"][0]["task_id"], "task-1")

    def test_history_preserves_task_id(self) -> None:
        from min_agent.trace_recorder import TraceRecorder

        recorder = TraceRecorder(user_goal="goal", workspace="workspace")
        recorder.emit("task_started", "running", "开始", task_id="task-1")
        recorder.emit("tool_started", "running", "调用工具")

        events = recorder.history()
        self.assertEqual(events[0].task_id, "task-1")
        self.assertIsNone(events[1].task_id)


class TraceRecorderV09Test(unittest.TestCase):
    def test_next_step_matches_next_emitted_event(self) -> None:
        from min_agent.trace_recorder import TraceRecorder

        recorder = TraceRecorder("goal", "workspace", run_id="run-1")
        self.assertEqual(recorder.next_step(), 1)
        event = recorder.emit("run_started", "running", "start")
        self.assertEqual(event.step, 1)
        self.assertEqual(recorder.next_step(), 2)
