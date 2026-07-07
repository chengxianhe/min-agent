from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class ContextBuilderTest(unittest.TestCase):
    def test_build_context_contains_goal_workspace_tools_and_observations(self) -> None:
        from min_agent.context_builder import ContextBuilder
        from min_agent.types import Observation, ToolResult, ToolSpec

        builder = ContextBuilder()
        observation = Observation(
            tool_name="read_file",
            args={"path": "notes.md"},
            result=ToolResult(success=True, content="hello"),
        )

        context = builder.build(
            user_goal="请读取 notes.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[observation],
        )

        self.assertEqual(context.user_goal, "请读取 notes.md 并总结")
        self.assertEqual(context.workspace, "examples/workspace")
        self.assertEqual(context.available_tools[0].name, "read_file")
        self.assertEqual(context.observations[0].result.content, "hello")


    def test_build_context_contains_all_v06_fields(self) -> None:
        from min_agent.context_builder import ContextBuilder
        from min_agent.types import Observation, ToolResult, ToolSpec

        builder = ContextBuilder()
        observation = Observation(
            tool_name="read_file",
            args={"path": "notes.md"},
            result=ToolResult(success=True, content="hello"),
        )

        context = builder.build(
            user_goal="请读取 notes.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[observation],
            selected_project_content=["notes.md"],
            run_id="test-run",
            started_at="2026-06-30T10:00:00+08:00",
        )

        self.assertEqual(context.selected_project_content, ["notes.md"])
        # Without ContextLoader, V0.6 fields should be None/empty
        self.assertIsNone(context.run_metadata)
        self.assertIsNone(context.workspace_config)
        self.assertIsNone(context.run_memory)
        self.assertEqual(context.tool_catalog, [])

    def test_base_context_loaded_only_once(self) -> None:
        from min_agent.context_builder import ContextBuilder
        from min_agent.context_loader import ContextLoader
        from min_agent.types import Observation, ToolResult, ToolSpec

        with __import__("tempfile").TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "ws"
            workspace.mkdir()
            runs_dir = Path(tmp) / "runs"
            runs_dir.mkdir()
            (workspace / "minagent.md").write_text("rule", encoding="utf-8")

            loader = ContextLoader(workspace=str(workspace), runs_dir=str(runs_dir), decision_model="fake")
            observation = Observation(
                tool_name="read_file",
                args={"path": "notes.md"},
                result=ToolResult(success=True, content="hello"),
            )

            builder = ContextBuilder(context_loader=loader)
            context1 = builder.build(
                user_goal="goal",
                workspace=str(workspace),
                available_tools=[ToolSpec(name="read_file", description="Read")],
                observations=[],
                run_id="r1",
                started_at="2026-06-30T10:00:00+08:00",
            )
            # Should have loaded workspace_config
            self.assertIsNotNone(context1.workspace_config)
            self.assertEqual(context1.workspace_config.status, "loaded")

            context2 = builder.build(
                user_goal="goal",
                workspace=str(workspace),
                available_tools=[ToolSpec(name="read_file", description="Read")],
                observations=[observation],
                run_id="r1",
                started_at="2026-06-30T10:00:00+08:00",
            )
            # Second call should still have the same workspace config
            self.assertEqual(context2.workspace_config.status, "loaded")

    def test_selected_project_content_passed_through(self) -> None:
        from min_agent.context_builder import ContextBuilder
        from min_agent.types import Observation, ToolResult, ToolSpec

        builder = ContextBuilder()
        context = builder.build(
            user_goal="goal",
            workspace="ws",
            available_tools=[],
            observations=[],
            selected_project_content=["a.md", "b.md"],
        )

        self.assertEqual(
            context.selected_project_content,
            ["a.md", "b.md"],
        )


if __name__ == "__main__":
    unittest.main()


# ===== V0.8 新增测试 =====


class ContextBuilderV08Test(unittest.TestCase):
    def test_build_with_task_plan(self) -> None:
        from min_agent.context_builder import ContextBuilder
        from min_agent.types import TaskSnapshot, ToolSpec

        builder = ContextBuilder()
        plan = [TaskSnapshot("task-1", "查看文件", "目录成功", "running")]
        context = builder.build(
            user_goal="复合目标",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="list_dir", description="List dir")],
            observations=[],
            task_plan=plan,
            current_task_id="task-1",
        )

        self.assertEqual(context.task_plan, plan)
        self.assertEqual(context.current_task_id, "task-1")
        data = context.to_dict()
        self.assertIn("task_plan", data)
        self.assertEqual(data["task_plan"][0]["task_id"], "task-1")
        self.assertEqual(data["current_task_id"], "task-1")

    def test_build_without_task_plan_v07_regression(self) -> None:
        from min_agent.context_builder import ContextBuilder
        from min_agent.types import ToolSpec

        builder = ContextBuilder()
        context = builder.build(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="run_command", description="Run command")],
            observations=[],
        )

        self.assertEqual(context.task_plan, [])
        self.assertIsNone(context.current_task_id)
        data = context.to_dict()
        self.assertNotIn("task_plan", data)
        self.assertNotIn("current_task_id", data)
