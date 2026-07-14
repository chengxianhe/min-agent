from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class AgentLoopTest(unittest.TestCase):
    def test_loop_reads_file_and_returns_final_answer(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.fake_llm import FakeLLM
        from min_agent.tool_registry import ToolRegistry
        from min_agent.tools.workspace import read_file
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import ToolSpec

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "notes.md").write_text("# 示例\n这是 Agent demo。", encoding="utf-8")

            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="read_file", description="Read file", args_schema={"path": "string"}),
                lambda args: read_file(workspace, args),
            )
            recorder = TraceRecorder(user_goal="请读取 notes.md 并总结", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=FakeLLM(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=5,
                step_delay_seconds=0,
            )

            result = loop.run("请读取 notes.md 并总结")

        self.assertTrue(result.success)
        self.assertIn("notes.md", result.message)
        self.assertTrue(any(event.phase == "tool_finished" for event in recorder.history()))
        self.assertTrue(any(event.phase == "final_answer" for event in recorder.history()))

    def test_loop_stops_when_file_is_missing(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.fake_llm import FakeLLM
        from min_agent.tool_registry import ToolRegistry
        from min_agent.tools.workspace import read_file
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import ToolSpec

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="read_file", description="Read file", args_schema={"path": "string"}),
                lambda args: read_file(workspace, args),
            )
            recorder = TraceRecorder(user_goal="请读取 missing.md 并总结", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=FakeLLM(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=5,
                step_delay_seconds=0,
            )

            result = loop.run("请读取 missing.md 并总结")

        self.assertFalse(result.success)
        self.assertIn("读取文件失败", result.message)
        self.assertTrue(any(event.status == "failed" for event in recorder.history()))

    def test_loop_stops_at_max_turns(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class AlwaysToolCallLLM:
            def decide(self, context: AgentContext) -> AgentAction:
                return AgentAction.tool_call(
                    tool_name="echo",
                    args={},
                    reason="测试最大轮次保护",
                )

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="echo", description="Echo"),
            lambda args: ToolResult(success=True, content="again"),
        )
        recorder = TraceRecorder(user_goal="loop forever", workspace="workspace")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=AlwaysToolCallLLM(),
            tools=registry,
            recorder=recorder,
            workspace="workspace",
            max_turns=2,
            step_delay_seconds=0,
        )

        result = loop.run("loop forever")

        self.assertFalse(result.success)
        self.assertIn("最大轮次", result.message)
        self.assertTrue(any(event.phase == "run_failed" for event in recorder.history()))

    def test_loop_uses_registry_for_model_tool_call(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class ToolCallModel:
            def __init__(self) -> None:
                self.calls = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self.calls += 1
                if self.calls == 1:
                    return AgentAction.tool_call("registered_tool", {}, "需要调用注册工具")
                return AgentAction.final_answer("done", "工具已调用")

        registry = ToolRegistry()
        calls = []
        registry.register(
            ToolSpec(name="registered_tool", description="Registered test tool"),
            lambda args: calls.append(args) or ToolResult(success=True, content="ok"),
        )
        recorder = TraceRecorder(user_goal="goal", workspace="workspace")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=ToolCallModel(),
            tools=registry,
            recorder=recorder,
            workspace="workspace",
            step_delay_seconds=0,
        )

        result = loop.run("goal")

        self.assertTrue(result.success)
        self.assertEqual(calls, [{}])


    def test_loop_can_discover_and_read_multiple_workspace_files(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.fake_llm import FakeLLM
        from min_agent.tool_registry import ToolRegistry
        from min_agent.tools.workspace import list_dir, read_file
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import ToolSpec

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "project.md").write_text("# 项目\nAgent demo", encoding="utf-8")
            (workspace / "architecture.md").write_text("# 架构\nAgentLoop", encoding="utf-8")

            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="read_file", description="Read file", args_schema={"path": "string"}),
                lambda args: read_file(workspace, args),
            )
            registry.register(
                ToolSpec(name="list_dir", description="List directory", args_schema={"path": "string"}),
                lambda args: list_dir(workspace, args),
            )
            recorder = TraceRecorder(user_goal="请总结这个工作区", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=FakeLLM(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                step_delay_seconds=0,
            )

            result = loop.run("请总结这个工作区")

        self.assertTrue(result.success)
        self.assertIn("project.md", result.message)
        self.assertIn("architecture.md", result.message)
        phases = [event.phase for event in recorder.history()]
        self.assertIn("tool_started", phases)
        tool_names = [
            event.input.get("tool_name")
            for event in recorder.history()
            if event.phase == "tool_started"
        ]
        self.assertIn("list_dir", tool_names)
        self.assertIn("read_file", tool_names)


    def test_selected_project_content_tracks_read_files(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.fake_llm import FakeLLM
        from min_agent.tool_registry import ToolRegistry
        from min_agent.tools.workspace import read_file
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import ToolSpec

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "notes.md").write_text("# 示例\n内容", encoding="utf-8")

            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="read_file", description="Read file", args_schema={"path": "string"}),
                lambda args: read_file(workspace, args),
            )
            recorder = TraceRecorder(user_goal="读取 notes.md", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=FakeLLM(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                step_delay_seconds=0,
            )

            result = loop.run("读取 notes.md")

        self.assertTrue(result.success)
        context_built_events = [
            event for event in recorder.history() if event.phase == "context_built"
        ]
        # The last context_built should have selected_project_content with notes.md
        if context_built_events:
            last_context = context_built_events[-1]
            spc = last_context.output.get("selected_project_content", [])
            self.assertIn("notes.md", spc)

    def test_selected_project_content_no_duplicates(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class MultiReadLLM:
            def __init__(self) -> None:
                self.calls = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self.calls += 1
                if self.calls <= 2:
                    return AgentAction.tool_call("read_file", {"path": "same.md"}, "read same file twice")
                return AgentAction.final_answer("done", "all done")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "same.md").write_text("content", encoding="utf-8")

            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="read_file", description="Read file", args_schema={"path": "string"}),
                lambda args: ToolResult(success=True, content="content", metadata={"path": str(args.get("path", ""))}),
            )
            recorder = TraceRecorder(user_goal="read twice", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=MultiReadLLM(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                step_delay_seconds=0,
            )

            loop.run("read twice")

        # After both reads, selected_project_content should only contain same.md once
        same_count = loop._selected_project_content.count("same.md")
        self.assertEqual(same_count, 1)

    def test_context_built_event_has_v06_fields(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext

        class SingleReadLLM:
            def decide(self, context: AgentContext) -> AgentAction:
                return AgentAction.final_answer("done", "done")

        registry = ToolRegistry()
        recorder = TraceRecorder(user_goal="test v06 fields", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=SingleReadLLM(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        loop.run("test v06 fields")

        context_built_events = [
            event for event in recorder.history() if event.phase == "context_built"
        ]
        self.assertGreater(len(context_built_events), 0)
        output = context_built_events[0].output
        # Core fields always present in context_built output
        self.assertIn("user_goal", output)
        self.assertIn("workspace", output)
        self.assertIn("available_tools", output)
        self.assertIn("observations", output)


if __name__ == "__main__":
    unittest.main()


# ===== V0.8 新增测试 =====


class AgentLoopV08SuccessTest(unittest.TestCase):
    def test_scripted_two_task_plan_completes_successfully(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.task_plan import TaskPlan
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskArtifactDraft, TaskDefinition, ToolResult, ToolSpec

        class ScriptedPlanModel:
            def __init__(self) -> None:
                self._step = 0
                self.contexts: list[AgentContext] = []

            def decide(self, context: AgentContext) -> AgentAction:
                self.contexts.append(context)
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "读取项目", "成功读取 project.md"),
                            TaskDefinition("task-2", "读取资料", "成功读取 notes.md"),
                        ],
                        "Composite goal needs two outcomes",
                    )
                elif self._step == 2:
                    return AgentAction.tool_call("read_file", {"path": "project.md"}, "Need project")
                elif self._step == 3:
                    return AgentAction.complete_task(
                        "task-1", "read_file succeeded", [1], "Criterion met",
                        task_artifact=TaskArtifactDraft("项目摘要", "project content")
                    )
                elif self._step == 4:
                    return AgentAction.tool_call("read_file", {"path": "notes.md"}, "Need content")
                elif self._step == 5:
                    return AgentAction.complete_task(
                        "task-2", "read_file succeeded", [1], "Criterion met",
                        task_artifact=TaskArtifactDraft("资料摘要", "file content")
                    )
                else:
                    return AgentAction.final_answer("done", "All tasks completed")

        model = ScriptedPlanModel()
        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="read_file", description="Read file"),
            lambda args: ToolResult(
                success=True,
                content=(
                    "project content"
                    if args.get("path") == "project.md"
                    else "file content"
                ),
            ),
        )
        recorder = TraceRecorder(user_goal="复合目标", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=model,
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("复合目标")
        self.assertTrue(result.success)

        events = recorder.history()
        phases = [e.phase for e in events]

        # plan_created 在第一个 tool_started 之前
        plan_idx = phases.index("plan_created")
        first_tool_idx = phases.index("tool_started")
        self.assertLess(plan_idx, first_tool_idx)

        # plan_created snapshot 包含两个 pending 任务
        plan_event = events[plan_idx]
        tasks = plan_event.output.get("tasks", [])
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["status"], "pending")
        self.assertEqual(tasks[1]["status"], "pending")

        # 每个 task_started 快照只有一个 running 任务
        task_started_events = [e for e in events if e.phase == "task_started"]
        self.assertGreaterEqual(len(task_started_events), 1)

        # tool_started 携带正确的 task_id
        for e in events:
            if e.phase == "tool_started":
                self.assertIsNotNone(e.task_id)
            if e.phase == "observation_added":
                self.assertIsNotNone(e.task_id)

        # task_completed(task-1) 在 task_started(task-2) 之前
        completed_phases = [
            (e.phase, e.output.get("task_id") if hasattr(e, "task_id") else e.task_id)
            for e in events
            if e.phase in ("task_completed", "task_started")
        ]
        task1_completed_idx = next(
            i for i, (p, _) in enumerate(completed_phases) if p == "task_completed"
        )
        task2_started_idx = next(
            i for i, (p, _) in enumerate(completed_phases)
            if p == "task_started" and i > task1_completed_idx
        )
        self.assertLess(task1_completed_idx, task2_started_idx)

        task1_contexts = [
            context for context in model.contexts
            if context.current_task_id == "task-1"
        ]
        task2_contexts = [
            context for context in model.contexts
            if context.current_task_id == "task-2"
        ]
        final_context = model.contexts[-1]

        self.assertEqual(task1_contexts[0].inherited_task_artifacts, [])
        self.assertEqual(
            [artifact.task_id for artifact in task2_contexts[0].inherited_task_artifacts],
            ["task-1"],
        )
        self.assertEqual(task2_contexts[0].observations, [])
        self.assertEqual(task2_contexts[0].selected_project_content, [])
        self.assertEqual(task2_contexts[-1].selected_project_content, ["notes.md"])

        self.assertIsNone(final_context.current_task_id)
        self.assertEqual(final_context.observations, [])
        self.assertEqual(final_context.selected_project_content, [])
        self.assertEqual(
            [artifact.task_id for artifact in final_context.inherited_task_artifacts],
            ["task-1", "task-2"],
        )

        artifact_events = [
            event for event in events if event.phase == "task_artifact_created"
        ]
        self.assertEqual(
            [event.task_id for event in artifact_events],
            ["task-1", "task-2"],
        )
        for event in artifact_events:
            event_index = events.index(event)
            self.assertEqual(events[event_index + 1].phase, "task_completed")
            self.assertEqual(events[event_index + 1].task_id, event.task_id)
            self.assertEqual(
                event.output["artifact"]["created_at_step"],
                event.step,
            )
            self.assertEqual(
                event.output["evidence_observations"],
                [{
                    "index": 1,
                    "tool_name": "read_file",
                    "args": {
                        "path": "project.md" if event.task_id == "task-1" else "notes.md"
                    },
                    "success": True,
                }],
            )

        lifecycle = [
            event.phase for event in events
            if event.phase in {
                "plan_created",
                "task_started",
                "task_artifact_created",
                "task_completed",
                "final_answer",
                "run_completed",
            }
        ]
        self.assertEqual(
            lifecycle,
            [
                "plan_created",
                "task_started",
                "task_artifact_created",
                "task_completed",
                "task_started",
                "task_artifact_created",
                "task_completed",
                "final_answer",
                "run_completed",
            ],
        )

    def test_scripted_model_task_order_matches_plan(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskArtifactDraft, TaskDefinition, ToolResult, ToolSpec

        class ThreeTaskModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "T1", "C1"),
                            TaskDefinition("task-2", "T2", "C2"),
                            TaskDefinition("task-3", "T3", "C3"),
                        ],
                        "Three tasks",
                    )
                elif self._step == 2:
                    return AgentAction.tool_call("tool_a", {}, "task 1 tool")
                elif self._step == 3:
                    return AgentAction.complete_task("task-1", "done", [1], "ok", task_artifact=TaskArtifactDraft("T1 产物", "a"))
                elif self._step == 4:
                    return AgentAction.tool_call("tool_b", {}, "task 2 tool")
                elif self._step == 5:
                    return AgentAction.complete_task("task-2", "done", [1], "ok", task_artifact=TaskArtifactDraft("T2 产物", "b"))
                elif self._step == 6:
                    return AgentAction.tool_call("tool_c", {}, "task 3 tool")
                elif self._step == 7:
                    return AgentAction.complete_task("task-3", "done", [1], "ok", task_artifact=TaskArtifactDraft("T3 产物", "c"))
                else:
                    return AgentAction.final_answer("all done", "completed")

        registry = ToolRegistry()
        for name in ("tool_a", "tool_b", "tool_c"):
            registry.register(
                ToolSpec(name=name, description=name),
                lambda args, n=name: ToolResult(success=True, content=n),
            )
        recorder = TraceRecorder(user_goal="three tasks", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=ThreeTaskModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("three tasks")
        self.assertTrue(result.success)

        events = recorder.history()
        task_started_ids = [
            e.output.get("task_id") for e in events if e.phase == "task_started"
        ]
        self.assertEqual(task_started_ids, ["task-1", "task-2", "task-3"])


class AgentLoopV08FailureTest(unittest.TestCase):
    def _make_registry(self) -> ToolRegistry:
        from min_agent.tool_registry import ToolRegistry
        from min_agent.types import ToolResult, ToolSpec

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="list_dir", description="List directory"),
            lambda args: ToolResult(success=True, content="notes.md"),
        )
        registry.register(
            ToolSpec(name="read_file", description="Read file"),
            lambda args: ToolResult(success=True, content="content"),
        )
        return registry

    def test_tool_failure_fails_current_and_skips_remaining(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskArtifactDraft, TaskDefinition, ToolResult, ToolSpec

        class FailingToolModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "T1", "C1"),
                            TaskDefinition("task-2", "T2", "C2"),
                        ],
                        "Plan",
                    )
                elif self._step == 2:
                    return AgentAction.tool_call("list_dir", {}, "tool call")
                else:
                    return AgentAction.final_answer("failed", "should not reach", success=False)

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="list_dir", description="List"),
            lambda args: ToolResult(success=False, error="read_failed"),
        )
        recorder = TraceRecorder(user_goal="fail", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=FailingToolModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("fail")
        self.assertFalse(result.success)

        events = recorder.history()
        phases = [e.phase for e in events]
        self.assertIn("task_failed", phases)
        self.assertIn("task_skipped", phases)
        self.assertIn("run_failed", phases)

        # 确认 final_answer 和 run_failed 的 task_id 为 None
        final_answer_events = [e for e in events if e.phase == "final_answer"]
        if final_answer_events:
            self.assertIsNone(final_answer_events[0].task_id)

    def test_permission_rejection_fails_current_task(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskArtifactDraft, TaskDefinition, ToolResult, ToolSpec

        class WriteInTaskModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "T1", "C1"),
                            TaskDefinition("task-2", "T2", "C2"),
                        ],
                        "Plan",
                    )
                elif self._step == 2:
                    return AgentAction.tool_call(
                        "write_file", {"path": "out.md", "content": "x"}, "write"
                    )
                else:
                    return AgentAction.final_answer("done", "ok")

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="write_file", description="Write", requires_permission=True),
            lambda args: ToolResult(success=True, content="written"),
        )
        recorder = TraceRecorder(user_goal="write", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=WriteInTaskModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
            permission_callback=lambda _a, _d: False,
        )

        result = loop.run("write")
        self.assertFalse(result.success)

        events = recorder.history()
        phases = [e.phase for e in events]
        self.assertIn("task_failed", phases)
        self.assertIn("task_skipped", phases)

        # 确保没有 tool_started 事件
        tool_started = [e for e in events if e.phase == "tool_started"]
        self.assertEqual(tool_started, [])

    def test_failure_transition_error_emits_deterministic_run_failure(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.task_plan import TaskPlan, TaskPlanError
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskDefinition, ToolResult, ToolSpec

        class FailingToolModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "T1", "C1"),
                            TaskDefinition("task-2", "T2", "C2"),
                        ],
                        "Plan",
                    )
                return AgentAction.tool_call("read_file", {"path": "x.md"}, "fail")

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="read_file", description="Read"),
            lambda args: ToolResult(success=False, error="read failed"),
        )
        recorder = TraceRecorder(user_goal="fail transition", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=FailingToolModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        with patch.object(
            TaskPlan,
            "fail_current",
            side_effect=TaskPlanError("forced-local-state-error"),
        ):
            result = loop.run("fail transition")

        self.assertFalse(result.success)
        self.assertEqual(
            result.message,
            "任务失败状态转换异常：forced-local-state-error",
        )
        terminal_events = [
            event for event in recorder.history()
            if event.phase in ("final_answer", "run_failed")
        ]
        self.assertEqual(
            [(event.phase, event.reason, event.task_id) for event in terminal_events],
            [
                ("final_answer", result.message, None),
                ("run_failed", result.message, None),
            ],
        )
        self.assertNotIn(
            "task_failed",
            [event.phase for event in recorder.history()],
        )

    def test_complete_task_wrong_id_fails(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskDefinition, ToolResult, ToolSpec

        class WrongIdModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "T1", "C1"),
                            TaskDefinition("task-2", "T2", "C2"),
                        ],
                        "Plan",
                    )
                elif self._step == 2:
                    return AgentAction.tool_call("list_dir", {}, "tool")
                elif self._step == 3:
                    # 错误：试图完成任务 2，但当前运行的是任务 1
                    return AgentAction.complete_task("task-2", "done", [1], "wrong id")
                else:
                    return AgentAction.final_answer("done", "ok")

        registry = self._make_registry()
        recorder = TraceRecorder(user_goal="wrong id", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=WrongIdModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("wrong id")
        self.assertFalse(result.success)

    def test_complete_task_no_successful_observation_fails(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskDefinition

        class NoObsModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "T1", "C1"),
                            TaskDefinition("task-2", "T2", "C2"),
                        ],
                        "Plan",
                    )
                elif self._step == 2:
                    # 没有先调用工具，直接尝试完成任务
                    return AgentAction.complete_task("task-1", "done without tool", [], "no evidence")
                else:
                    return AgentAction.final_answer("done", "ok")

        registry = self._make_registry()
        recorder = TraceRecorder(user_goal="no obs", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=NoObsModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("no obs")
        self.assertFalse(result.success)

    def test_failed_final_answer_while_task_running(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskDefinition, ToolResult, ToolSpec

        class FailedFinalModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "T1", "C1"),
                            TaskDefinition("task-2", "T2", "C2"),
                        ],
                        "Plan",
                    )
                elif self._step == 2:
                    # 任务还在运行，直接返回失败
                    return AgentAction.final_answer("I give up", "cannot proceed", success=False)
                else:
                    return AgentAction.final_answer("done", "ok")

        registry = self._make_registry()
        recorder = TraceRecorder(user_goal="failed final", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=FailedFinalModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("failed final")
        self.assertFalse(result.success)
        events = recorder.history()
        phases = [e.phase for e in events]
        self.assertIn("task_failed", phases)
        self.assertIn("run_failed", phases)

    def test_successful_final_answer_before_all_completed_fails(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskDefinition

        class PrematureSuccessModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "T1", "C1"),
                            TaskDefinition("task-2", "T2", "C2"),
                        ],
                        "Plan",
                    )
                elif self._step == 2:
                    # 过早宣告成功，任务还没完成
                    return AgentAction.final_answer("all done", "premature", success=True)
                else:
                    return AgentAction.final_answer("done", "ok")

        registry = self._make_registry()
        recorder = TraceRecorder(user_goal="premature", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=PrematureSuccessModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("premature")
        self.assertFalse(result.success)

    def test_max_turns_exhausted_during_task_fails(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskDefinition, ToolResult, ToolSpec

        class LoopingModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "T1", "C1"),
                            TaskDefinition("task-2", "T2", "C2"),
                        ],
                        "Plan",
                    )
                else:
                    return AgentAction.tool_call("list_dir", {}, f"keep going {self._step}")

        registry = self._make_registry()
        recorder = TraceRecorder(user_goal="loop", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=LoopingModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            max_turns=4,
            step_delay_seconds=0,
        )

        result = loop.run("loop")
        self.assertFalse(result.success)
        events = recorder.history()
        phases = [e.phase for e in events]
        self.assertIn("task_failed", phases)
        self.assertIn("run_failed", phases)

    def test_create_plan_after_tool_started_is_illegal(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskDefinition, ToolResult, ToolSpec

        class LatePlanModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.tool_call("list_dir", {}, "normal tool call first")
                elif self._step == 2:
                    # 非法：工具已经调用过，不能再创建计划
                    return AgentAction.create_plan(
                        [TaskDefinition("task-1", "T1", "C1"), TaskDefinition("task-2", "T2", "C2")],
                        "late plan",
                    )
                else:
                    return AgentAction.final_answer("done", "ok")

        registry = self._make_registry()
        recorder = TraceRecorder(user_goal="late", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=LatePlanModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("late")
        self.assertFalse(result.success)
        events = recorder.history()
        # 不应出现 plan_created
        self.assertNotIn("plan_created", [e.phase for e in events])

    def test_duplicate_create_plan_is_illegal(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskDefinition

        class DoublePlanModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [TaskDefinition("task-1", "T1", "C1"), TaskDefinition("task-2", "T2", "C2")],
                        "first plan",
                    )
                elif self._step == 2:
                    # 非法：计划已存在
                    return AgentAction.create_plan(
                        [TaskDefinition("task-1", "T3", "C3"), TaskDefinition("task-2", "T4", "C4")],
                        "second plan",
                    )
                else:
                    return AgentAction.final_answer("done", "ok")

        registry = self._make_registry()
        recorder = TraceRecorder(user_goal="double", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=DoublePlanModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("double")
        self.assertFalse(result.success)
        # 只有一个 plan_created
        plan_created_count = sum(1 for e in recorder.history() if e.phase == "plan_created")
        self.assertEqual(plan_created_count, 1)


class AgentLoopV08RegressionTest(unittest.TestCase):
    def test_simple_goal_no_plan_events(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class SimpleModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call("read_file", {"path": "notes.md"}, "read")
                return AgentAction.final_answer("summary", "done")

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="read_file", description="Read"),
            lambda args: ToolResult(success=True, content="content"),
        )
        recorder = TraceRecorder(user_goal="简单目标", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=SimpleModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("简单目标")
        self.assertTrue(result.success)

        events = recorder.history()
        phases = [e.phase for e in events]
        self.assertNotIn("plan_created", phases)
        self.assertNotIn("task_started", phases)
        self.assertNotIn("task_completed", phases)
        self.assertNotIn("task_failed", phases)
        self.assertNotIn("task_skipped", phases)

        # 所有事件 task_id 为 None
        for e in events:
            self.assertIsNone(e.task_id)

    def test_simple_goal_tool_failure_continues_as_v07(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class SimpleFailModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.tool_call("read_file", {"path": "missing.md"}, "try read")
                elif self._step == 2:
                    # V0.7: 工具失败后模型收到 Observation，可以继续或最终失败
                    return AgentAction.final_answer("cannot read file", "file missing", success=False)
                return AgentAction.final_answer("done", "ok")

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="read_file", description="Read"),
            lambda args: ToolResult(success=False, error="file not found"),
        )
        recorder = TraceRecorder(user_goal="简单目标", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=SimpleFailModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("简单目标")
        self.assertFalse(result.success)
        # V0.7: 不产生 task_failed
        phases = [e.phase for e in recorder.history()]
        self.assertNotIn("task_failed", phases)


class AgentLoopV08BudgetTest(unittest.TestCase):
    def test_composite_run_uses_higher_default_budget(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskArtifactDraft, TaskDefinition, ToolResult, ToolSpec

        class LongPlanModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [
                            TaskDefinition("task-1", "T1", "C1"),
                            TaskDefinition("task-2", "T2", "C2"),
                        ],
                        "Plan",
                    )
                elif self._step <= 10:
                    # 9 次工具调用，超过默认简单目标 8 轮预算
                    return AgentAction.tool_call("list_dir", {}, f"step {self._step}")
                elif self._step == 11:
                    return AgentAction.complete_task("task-1", "done", [1], "ok", task_artifact=TaskArtifactDraft("T1 产物", "ok"))
                elif self._step == 12:
                    return AgentAction.tool_call("read_file", {"path": "x"}, "read")
                elif self._step == 13:
                    return AgentAction.complete_task("task-2", "done", [1], "ok", task_artifact=TaskArtifactDraft("T2 产物", "ok"))
                else:
                    return AgentAction.final_answer("completed", "all done")

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="list_dir", description="List"),
            lambda args: ToolResult(success=True, content="ok"),
        )
        registry.register(
            ToolSpec(name="read_file", description="Read"),
            lambda args: ToolResult(success=True, content="ok"),
        )
        recorder = TraceRecorder(user_goal="long plan", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=LongPlanModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("long plan")
        self.assertTrue(result.success)
        # 应该超过 8 轮（默认简单预算），在复合预算 20 轮内完成
        decisions = sum(1 for e in recorder.history() if e.phase == "llm_decision")
        self.assertGreater(decisions, 8)

    def test_simple_goal_stops_at_v07_default_eight_turns(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class LoopingModel:
            def decide(self, context: AgentContext) -> AgentAction:
                return AgentAction.tool_call("echo", {}, "loop")

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="echo", description="Echo"),
            lambda args: ToolResult(success=True, content="again"),
        )
        recorder = TraceRecorder(user_goal="simple loop", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=LoopingModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("simple loop")
        self.assertFalse(result.success)
        decisions = sum(1 for e in recorder.history() if e.phase == "llm_decision")
        self.assertEqual(decisions, 8)

    def test_delayed_create_plan_exhausts_simple_budget(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskDefinition, ToolResult, ToolSpec

        class DelayedPlanModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step <= 9:
                    # 先消耗 9 轮不创建计划
                    return AgentAction.tool_call("echo", {}, f"step {self._step}")
                # 第 10 轮尝试创建计划——但简单预算只有 8 轮，到不了这里
                return AgentAction.create_plan(
                    [TaskDefinition("task-1", "T1", "C1"), TaskDefinition("task-2", "T2", "C2")],
                    "late",
                )

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="echo", description="Echo"),
            lambda args: ToolResult(success=True, content="ok"),
        )
        recorder = TraceRecorder(user_goal="delayed", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=DelayedPlanModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            step_delay_seconds=0,
        )

        result = loop.run("delayed")
        self.assertFalse(result.success)
        # 应在 8 轮时因为简单预算耗尽而失败
        self.assertNotIn("plan_created", [e.phase for e in recorder.history()])

    def test_explicit_lower_max_turns_truncates_composite(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, TaskDefinition, ToolResult, ToolSpec

        class LoopingPlanModel:
            def __init__(self) -> None:
                self._step = 0

            def decide(self, context: AgentContext) -> AgentAction:
                self._step += 1
                if self._step == 1:
                    return AgentAction.create_plan(
                        [TaskDefinition("task-1", "T1", "C1"), TaskDefinition("task-2", "T2", "C2")],
                        "Plan",
                    )
                else:
                    return AgentAction.tool_call("echo", {}, f"step {self._step}")

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="echo", description="Echo"),
            lambda args: ToolResult(success=True, content="ok"),
        )
        recorder = TraceRecorder(user_goal="truncated", workspace="ws")
        loop = AgentLoop(
            context_builder=ContextBuilder(),
            llm=LoopingPlanModel(),
            tools=registry,
            recorder=recorder,
            workspace="ws",
            max_turns=5,
            step_delay_seconds=0,
        )

        result = loop.run("truncated")
        self.assertFalse(result.success)
        decisions = sum(1 for e in recorder.history() if e.phase == "llm_decision")
        self.assertEqual(decisions, 5)
