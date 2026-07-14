from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class CoreTypesTest(unittest.TestCase):
    def test_agent_action_tool_call_is_serializable(self) -> None:
        from min_agent.types import AgentAction

        action = AgentAction.tool_call(
            tool_name="read_file",
            args={"path": "notes.md"},
            reason="需要读取文件内容后才能总结",
            metadata={"model_call": {"provider": "deepseek"}},
        )

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.to_dict()["tool_name"], "read_file")
        self.assertEqual(action.to_dict()["args"], {"path": "notes.md"})
        self.assertEqual(action.to_dict()["metadata"]["model_call"]["provider"], "deepseek")

    def test_observation_wraps_tool_result(self) -> None:
        from min_agent.types import Observation, ToolResult

        observation = Observation(
            tool_name="read_file",
            args={"path": "notes.md"},
            result=ToolResult(success=True, content="hello"),
        )

        data = observation.to_dict()
        self.assertTrue(data["result"]["success"])
        self.assertEqual(data["result"]["content"], "hello")

    def test_trace_event_is_serializable(self) -> None:
        from min_agent.types import TraceEvent

        event = TraceEvent(
            run_id="run-1",
            step=1,
            timestamp="2026-06-17T16:00:00+08:00",
            phase="llm_decision",
            status="running",
            title="决定下一步",
            reason="还没有文件内容",
            input={"observations": []},
            output={"action": "read_file"},
        )

        data = event.to_dict()
        self.assertEqual(data["phase"], "llm_decision")
        self.assertEqual(data["output"]["action"], "read_file")

    def test_agent_run_result_is_serializable(self) -> None:
        from min_agent.types import AgentRunResult

        result = AgentRunResult(message="done", success=True)

        self.assertEqual(result.to_dict(), {"message": "done", "success": True})

    def test_trace_event_with_permission_requested_phase(self) -> None:
        from min_agent.types import TraceEvent

        event = TraceEvent(
            run_id="run-1",
            step=5,
            timestamp="2026-06-23T16:00:00+08:00",
            phase="permission_requested",
            status="waiting",
            title="请求权限：write_file",
            reason="需要用户批准写文件",
            input={"tool_name": "write_file", "args": {"path": "summary.md"}, "preview": "# Summary\n..."},
            output={},
        )

        data = event.to_dict()
        self.assertEqual(data["phase"], "permission_requested")
        self.assertEqual(data["input"]["tool_name"], "write_file")

    def test_trace_event_with_permission_resolved_phase(self) -> None:
        from min_agent.types import TraceEvent

        event = TraceEvent(
            run_id="run-1",
            step=6,
            timestamp="2026-06-23T16:00:01+08:00",
            phase="permission_resolved",
            status="completed",
            title="权限已批准",
            reason="用户批准执行 write_file",
            input={"tool_name": "write_file", "args": {"path": "summary.md"}},
            output={"approved": True},
        )

        data = event.to_dict()
        self.assertEqual(data["phase"], "permission_resolved")
        self.assertTrue(data["output"]["approved"])


# ===== V0.8 新增测试 =====


class TaskDefinitionTest(unittest.TestCase):
    def test_task_definition_is_frozen_and_serializable(self) -> None:
        from min_agent.types import TaskDefinition

        task = TaskDefinition(
            task_id="task-1",
            title="查看项目文件",
            completion_criteria="成功获得 workspace 根目录文件列表。",
        )
        self.assertEqual(task.task_id, "task-1")
        self.assertEqual(task.title, "查看项目文件")
        self.assertEqual(task.completion_criteria, "成功获得 workspace 根目录文件列表。")

        data = task.to_dict()
        self.assertEqual(data["task_id"], "task-1")
        self.assertEqual(data["title"], "查看项目文件")
        self.assertEqual(data["completion_criteria"], "成功获得 workspace 根目录文件列表。")

    def test_task_definition_is_immutable(self) -> None:
        from min_agent.types import TaskDefinition

        task = TaskDefinition("task-1", "标题", "标准")
        with self.assertRaises(Exception):
            task.task_id = "task-2"  # type: ignore[misc]


class TaskSnapshotTest(unittest.TestCase):
    def test_task_snapshot_defaults(self) -> None:
        from min_agent.types import TaskSnapshot

        snap = TaskSnapshot(
            task_id="task-1",
            title="查看文件",
            completion_criteria="获得文件列表",
            status="pending",
        )
        self.assertEqual(snap.failure_reason, "")

    def test_task_snapshot_with_failure(self) -> None:
        from min_agent.types import TaskSnapshot

        snap = TaskSnapshot(
            task_id="task-2",
            title="读取资料",
            completion_criteria="成功读取",
            status="failed",
            failure_reason="permission denied",
        )
        data = snap.to_dict()
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["failure_reason"], "permission denied")


class TaskArtifactV09Test(unittest.TestCase):
    def test_runtime_artifact_and_draft_keep_trust_boundary(self) -> None:
        from min_agent.types import AgentAction, TaskArtifact, TaskArtifactDraft

        draft = TaskArtifactDraft("项目资料摘要", "summary text")
        artifact = TaskArtifact("task-2", draft.title, draft.content, [1, 2], 12, "available")
        action = AgentAction.complete_task("task-2", "reads succeeded", [1, 2], "criterion met", task_artifact=draft)

        self.assertEqual(artifact.to_dict()["evidence_observation_indexes"], [1, 2])
        self.assertEqual(action.to_dict()["task_artifact"], draft.to_dict())
        self.assertNotIn("created_at_step", draft.to_dict())


class AgentActionV08Test(unittest.TestCase):
    def test_create_plan_action(self) -> None:
        from min_agent.types import AgentAction, TaskDefinition

        tasks = [
            TaskDefinition("task-1", "查看项目文件", "成功获得 workspace 根目录文件列表。"),
        ]
        action = AgentAction.create_plan(tasks, reason="Need an explicit plan")
        self.assertEqual(action.kind, "create_plan")
        self.assertEqual(len(action.tasks), 1)
        self.assertEqual(action.tasks[0].task_id, "task-1")

        data = action.to_dict()
        self.assertEqual(data["kind"], "create_plan")
        self.assertEqual(data["tasks"][0]["task_id"], "task-1")
        self.assertEqual(data["tasks"][0]["title"], "查看项目文件")

    def test_complete_task_action(self) -> None:
        from min_agent.types import AgentAction

        completion = AgentAction.complete_task(
            task_id="task-1",
            completion_evidence="list_dir Observation succeeded",
            evidence_observation_indexes=[1],
            reason="The criterion is satisfied",
        )
        self.assertEqual(completion.kind, "complete_task")
        self.assertEqual(completion.task_id, "task-1")
        self.assertEqual(completion.completion_evidence, "list_dir Observation succeeded")
        self.assertEqual(completion.evidence_observation_indexes, [1])

        data = completion.to_dict()
        self.assertEqual(data["kind"], "complete_task")
        self.assertEqual(data["task_id"], "task-1")
        self.assertEqual(data["evidence_observation_indexes"], [1])

    def test_tool_call_v07_defaults_preserved(self) -> None:
        from min_agent.types import AgentAction

        action = AgentAction.tool_call("read_file", {"path": "notes.md"}, "需要读取")
        data = action.to_dict()
        # V0.7 默认值：tasks 为空，task_id 为 None
        self.assertEqual(data.get("tasks"), [])
        self.assertIsNone(data.get("task_id"))
        self.assertIsNone(data.get("completion_evidence"))
        self.assertEqual(data.get("evidence_observation_indexes"), [])

    def test_final_answer_v07_defaults_preserved(self) -> None:
        from min_agent.types import AgentAction

        action = AgentAction.final_answer("done", "all good")
        data = action.to_dict()
        self.assertEqual(data.get("tasks"), [])
        self.assertIsNone(data.get("task_id"))


class TraceEventV08Test(unittest.TestCase):
    def test_trace_event_with_task_id(self) -> None:
        from min_agent.types import TraceEvent

        event = TraceEvent(
            run_id="run-1",
            step=1,
            timestamp="2026-07-07T00:00:00+08:00",
            phase="task_started",
            status="running",
            title="开始任务",
            task_id="task-1",
        )
        self.assertEqual(event.task_id, "task-1")
        self.assertEqual(event.to_dict()["task_id"], "task-1")

    def test_trace_event_without_task_id_defaults_to_none(self) -> None:
        from min_agent.types import TraceEvent

        event = TraceEvent(
            run_id="run-1",
            step=1,
            timestamp="2026-07-07T00:00:00+08:00",
            phase="llm_decision",
            status="running",
            title="决定下一步",
        )
        self.assertIsNone(event.task_id)
        self.assertIsNone(event.to_dict()["task_id"])

    def test_new_event_phases_are_valid(self) -> None:
        from min_agent.types import TraceEvent

        for phase in ("plan_created", "task_started", "task_completed", "task_failed", "task_skipped"):
            event = TraceEvent(
                run_id="run-1",
                step=1,
                timestamp="2026-07-07T00:00:00+08:00",
                phase=phase,  # type: ignore[arg-type]
                status="running",
                title="测试",
            )
            self.assertEqual(event.phase, phase)


class AgentContextV08Test(unittest.TestCase):
    def test_context_with_task_plan(self) -> None:
        from min_agent.types import AgentContext, TaskSnapshot, ToolSpec

        plan = [TaskSnapshot("task-1", "查看文件", "获得列表", "running")]
        ctx = AgentContext(
            user_goal="测试",
            workspace="/tmp",
            available_tools=[ToolSpec("read_file", "读取文件")],
            observations=[],
            task_plan=plan,
            current_task_id="task-1",
        )
        self.assertEqual(ctx.task_plan, plan)
        self.assertEqual(ctx.current_task_id, "task-1")

        data = ctx.to_dict()
        self.assertIn("task_plan", data)
        self.assertEqual(data["task_plan"][0]["task_id"], "task-1")
        self.assertEqual(data["current_task_id"], "task-1")

    def test_context_without_task_plan(self) -> None:
        from min_agent.types import AgentContext, ToolSpec

        ctx = AgentContext(
            user_goal="现在几点？",
            workspace="/tmp",
            available_tools=[ToolSpec("run_command", "执行命令")],
            observations=[],
        )
        self.assertEqual(ctx.task_plan, [])
        self.assertIsNone(ctx.current_task_id)

        data = ctx.to_dict()
        # V0.7 兼容：无计划时不出现 task_plan
        self.assertNotIn("task_plan", data)
        self.assertNotIn("current_task_id", data)


if __name__ == "__main__":
    unittest.main()
