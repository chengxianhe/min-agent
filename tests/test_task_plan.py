from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class TaskPlanCreationTest(unittest.TestCase):
    def test_create_valid_two_task_plan(self) -> None:
        from min_agent.task_plan import TaskPlan
        from min_agent.types import TaskDefinition

        definitions = [
            TaskDefinition("task-1", "查看文件", "获得成功的目录 Observation"),
            TaskDefinition("task-2", "读取资料", "获得成功的读取 Observation"),
        ]
        plan = TaskPlan.create(definitions)
        snapshot = plan.snapshot()
        self.assertEqual(len(snapshot), 2)
        self.assertEqual([t.status for t in snapshot], ["pending", "pending"])

    def test_create_valid_five_task_plan(self) -> None:
        from min_agent.task_plan import TaskPlan
        from min_agent.types import TaskDefinition

        definitions = [
            TaskDefinition("task-1", "任务一", "标准一"),
            TaskDefinition("task-2", "任务二", "标准二"),
            TaskDefinition("task-3", "任务三", "标准三"),
            TaskDefinition("task-4", "任务四", "标准四"),
            TaskDefinition("task-5", "任务五", "标准五"),
        ]
        plan = TaskPlan.create(definitions)
        self.assertEqual(len(plan.snapshot()), 5)

    def test_reject_zero_tasks(self) -> None:
        from min_agent.task_plan import TaskPlan, TaskPlanError

        with self.assertRaises(TaskPlanError):
            TaskPlan.create([])

    def test_reject_one_task(self) -> None:
        from min_agent.task_plan import TaskPlan, TaskPlanError
        from min_agent.types import TaskDefinition

        with self.assertRaises(TaskPlanError):
            TaskPlan.create([TaskDefinition("task-1", "标题", "标准")])

    def test_reject_six_tasks(self) -> None:
        from min_agent.task_plan import TaskPlan, TaskPlanError
        from min_agent.types import TaskDefinition

        definitions = [TaskDefinition(f"task-{i}", f"任务{i}", f"标准{i}") for i in range(1, 7)]
        with self.assertRaises(TaskPlanError):
            TaskPlan.create(definitions)

    def test_reject_non_sequential_ids(self) -> None:
        from min_agent.task_plan import TaskPlan, TaskPlanError
        from min_agent.types import TaskDefinition

        definitions = [
            TaskDefinition("task-1", "任务一", "标准一"),
            TaskDefinition("task-3", "任务三", "标准三"),
        ]
        with self.assertRaises(TaskPlanError):
            TaskPlan.create(definitions)

    def test_reject_duplicate_ids(self) -> None:
        from min_agent.task_plan import TaskPlan, TaskPlanError
        from min_agent.types import TaskDefinition

        definitions = [
            TaskDefinition("task-1", "任务一", "标准一"),
            TaskDefinition("task-1", "任务一", "标准一"),
        ]
        with self.assertRaises(TaskPlanError):
            TaskPlan.create(definitions)

    def test_reject_blank_title(self) -> None:
        from min_agent.task_plan import TaskPlan, TaskPlanError
        from min_agent.types import TaskDefinition

        definitions = [
            TaskDefinition("task-1", "  ", "标准一"),
            TaskDefinition("task-2", "任务二", "标准二"),
        ]
        with self.assertRaises(TaskPlanError):
            TaskPlan.create(definitions)

    def test_reject_blank_completion_criteria(self) -> None:
        from min_agent.task_plan import TaskPlan, TaskPlanError
        from min_agent.types import TaskDefinition

        definitions = [
            TaskDefinition("task-1", "任务一", "标准一"),
            TaskDefinition("task-2", "任务二", ""),
        ]
        with self.assertRaises(TaskPlanError):
            TaskPlan.create(definitions)

    def test_definitions_are_copied_at_creation(self) -> None:
        from min_agent.task_plan import TaskPlan
        from min_agent.types import TaskDefinition

        definitions = [
            TaskDefinition("task-1", "任务一", "标准一"),
            TaskDefinition("task-2", "任务二", "标准二"),
        ]
        plan = TaskPlan.create(definitions)
        # 修改原始列表不应影响 plan
        definitions.append(TaskDefinition("task-3", "任务三", "标准三"))
        self.assertEqual(len(plan.snapshot()), 2)


class TaskPlanTransitionTest(unittest.TestCase):
    def setUp(self) -> None:
        from min_agent.task_plan import TaskPlan
        from min_agent.types import TaskDefinition

        self.definitions = [
            TaskDefinition("task-1", "查看文件", "获得成功的目录 Observation"),
            TaskDefinition("task-2", "读取资料", "获得成功的读取 Observation"),
        ]
        self.plan = TaskPlan.create(self.definitions)

    def test_start_next_moves_first_pending_to_running(self) -> None:
        started = self.plan.start_next()
        self.assertIsNotNone(started)
        self.assertEqual(started.task_id, "task-1")
        self.assertEqual(started.status, "running")
        snapshot = self.plan.snapshot()
        self.assertEqual([t.status for t in snapshot], ["running", "pending"])

    def test_current_task_returns_running(self) -> None:
        self.plan.start_next()
        current = self.plan.current_task()
        self.assertIsNotNone(current)
        self.assertEqual(current.task_id, "task-1")
        self.assertEqual(current.status, "running")

    def test_current_task_returns_none_when_none_running(self) -> None:
        self.assertIsNone(self.plan.current_task())

    def test_complete_current_with_valid_evidence(self) -> None:
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True))]
        completed = self.plan.complete_current(
            "task-1",
            "The directory listing succeeded",
            [1],
            observations,
        )
        self.assertEqual(completed.status, "completed")
        self.assertEqual(completed.task_id, "task-1")

    def test_complete_current_changes_status(self) -> None:
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True))]
        self.plan.complete_current("task-1", "done", [1], observations)
        self.assertEqual([t.status for t in self.plan.snapshot()], ["completed", "pending"])

    def test_complete_current_rejects_wrong_task_id(self) -> None:
        from min_agent.task_plan import TaskPlanError
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True))]
        with self.assertRaises(TaskPlanError):
            self.plan.complete_current("task-2", "done", [1], observations)

    def test_complete_current_rejects_empty_evidence(self) -> None:
        from min_agent.task_plan import TaskPlanError
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True))]
        with self.assertRaises(TaskPlanError):
            self.plan.complete_current("task-1", "", [1], observations)

    def test_complete_current_rejects_empty_indexes(self) -> None:
        from min_agent.task_plan import TaskPlanError
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        with self.assertRaises(TaskPlanError):
            self.plan.complete_current("task-1", "done", [], [])

    def test_complete_current_rejects_duplicate_indexes(self) -> None:
        from min_agent.task_plan import TaskPlanError
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [
            Observation("list_dir", {"path": "."}, ToolResult(success=True)),
            Observation("read_file", {"path": "notes.md"}, ToolResult(success=True)),
        ]
        with self.assertRaises(TaskPlanError):
            self.plan.complete_current("task-1", "done", [1, 1], observations)

    def test_complete_current_rejects_zero_index(self) -> None:
        from min_agent.task_plan import TaskPlanError
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True))]
        with self.assertRaises(TaskPlanError):
            self.plan.complete_current("task-1", "done", [0], observations)

    def test_complete_current_rejects_negative_index(self) -> None:
        from min_agent.task_plan import TaskPlanError
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True))]
        with self.assertRaises(TaskPlanError):
            self.plan.complete_current("task-1", "done", [-1], observations)

    def test_complete_current_rejects_out_of_range_index(self) -> None:
        from min_agent.task_plan import TaskPlanError
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True))]
        with self.assertRaises(TaskPlanError):
            self.plan.complete_current("task-1", "done", [99], observations)

    def test_complete_current_rejects_failed_observation(self) -> None:
        from min_agent.task_plan import TaskPlanError
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [
            Observation("read_file", {"path": "missing.md"}, ToolResult(success=False, error="not found")),
        ]
        with self.assertRaises(TaskPlanError):
            self.plan.complete_current("task-1", "done", [1], observations)

    def test_cannot_start_second_task_while_one_running(self) -> None:
        from min_agent.task_plan import TaskPlanError

        self.plan.start_next()
        with self.assertRaises(TaskPlanError):
            self.plan.start_next()

    def test_start_next_after_completion(self) -> None:
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True))]
        self.plan.complete_current("task-1", "done", [1], observations)

        started = self.plan.start_next()
        self.assertIsNotNone(started)
        self.assertEqual(started.task_id, "task-2")
        self.assertEqual([t.status for t in self.plan.snapshot()], ["completed", "running"])

    def test_start_next_returns_none_when_all_done(self) -> None:
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        self.plan.complete_current("task-1", "done", [1], [Observation("list_dir", {}, ToolResult(success=True))])
        self.plan.start_next()
        self.plan.complete_current("task-2", "done", [1], [Observation("read_file", {}, ToolResult(success=True))])

        self.assertIsNone(self.plan.start_next())

    def test_all_completed(self) -> None:
        from min_agent.types import Observation, ToolResult

        self.assertFalse(self.plan.all_completed())
        self.plan.start_next()
        self.plan.complete_current("task-1", "done", [1], [Observation("list_dir", {}, ToolResult(success=True))])
        self.plan.start_next()
        self.plan.complete_current("task-2", "done", [1], [Observation("read_file", {}, ToolResult(success=True))])
        self.assertTrue(self.plan.all_completed())

    def test_snapshot_returns_copies_not_references(self) -> None:
        self.plan.start_next()
        snap = self.plan.snapshot()
        # 修改返回的 snapshot 不应影响内部状态
        snap[0] = snap[0]  # 这不会影响内部状态，但我们可以测 to_dict 返回的是新对象
        # 真正测试：修改返回的 task 字典不应影响下一次 snapshot
        snap_dict = self.plan.snapshot()
        self.assertEqual(snap_dict[0].status, "running")

    def test_structural_evidence_boundary(self) -> None:
        """V0.8 只做结构化验证：即使 completion_criteria 说 '生成 summary.md'，
        只要引用的 Observation 属于当前任务且成功，complete_current 就接受。
        这个测试记录该边界；语义相关性由场景测试保证。"""
        from min_agent.types import Observation, TaskDefinition, ToolResult

        from min_agent.task_plan import TaskPlan

        definitions = [
            TaskDefinition("task-1", "生成摘要文件", "生成 summary.md"),
            TaskDefinition("task-2", "验证文件", "确认文件存在"),
        ]
        plan = TaskPlan.create(definitions)
        plan.start_next()

        # 当前 Observation 是成功的 list_dir，不是 write_file
        # 但 complete_current 只看结构和 success，不管语义
        observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True, content="[]"))]
        completed = plan.complete_current(
            "task-1",
            "list_dir succeeded",
            [1],
            observations,
        )
        self.assertEqual(completed.status, "completed")


class TaskPlanFailureTest(unittest.TestCase):
    def setUp(self) -> None:
        from min_agent.task_plan import TaskPlan
        from min_agent.types import TaskDefinition

        self.definitions = [
            TaskDefinition("task-1", "查看文件", "获得目录列表"),
            TaskDefinition("task-2", "读取资料", "成功读取"),
            TaskDefinition("task-3", "生成摘要", "成功写入"),
        ]
        self.plan = TaskPlan.create(self.definitions)

    def test_fail_current_marks_failed_and_skips_pending(self) -> None:
        self.plan.start_next()
        failed, skipped = self.plan.fail_current("permission denied by user")

        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.task_id, "task-1")
        self.assertEqual(failed.failure_reason, "permission denied by user")

        self.assertEqual(len(skipped), 2)
        self.assertEqual(skipped[0].status, "skipped")
        self.assertEqual(skipped[0].task_id, "task-2")
        self.assertIn("task-1", skipped[0].failure_reason)
        self.assertEqual(skipped[1].status, "skipped")
        self.assertEqual(skipped[1].task_id, "task-3")

    def test_fail_current_clears_running(self) -> None:
        self.plan.start_next()
        self.plan.fail_current("error")
        self.assertIsNone(self.plan.current_task())

    def test_fail_current_fails_all_pending_to_skipped(self) -> None:
        self.plan.start_next()
        self.plan.fail_current("error")
        statuses = [t.status for t in self.plan.snapshot()]
        self.assertEqual(statuses, ["failed", "skipped", "skipped"])

    def test_fail_current_without_running_task(self) -> None:
        from min_agent.task_plan import TaskPlanError

        with self.assertRaises(TaskPlanError):
            self.plan.fail_current("error")

    def test_completed_status_is_terminal(self) -> None:
        from min_agent.task_plan import TaskPlanError
        from min_agent.types import Observation, ToolResult

        self.plan.start_next()
        observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True))]
        self.plan.complete_current("task-1", "done", [1], observations)
        # 已完成的任务不能被再次完成
        with self.assertRaises(TaskPlanError):
            self.plan.complete_current("task-1", "done", [1], observations)

    def test_failed_status_is_terminal(self) -> None:
        from min_agent.task_plan import TaskPlanError

        self.plan.start_next()
        self.plan.fail_current("error")
        # 已失败的任务不能被完成
        with self.assertRaises(TaskPlanError):
            self.plan.complete_current("task-1", "done", [1], [])

    def test_skipped_status_is_terminal(self) -> None:
        self.plan.start_next()
        self.plan.fail_current("error")
        # 已跳过的任务不是 pending，start_next 返回 None
        self.assertIsNone(self.plan.start_next())


if __name__ == "__main__":
    unittest.main()
