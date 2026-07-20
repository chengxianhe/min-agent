from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class FakeLLMTest(unittest.TestCase):
    def test_decides_to_read_target_file_when_content_missing(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请读取 notes.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "read_file")
        self.assertEqual(action.args, {"path": "notes.md"})
        self.assertIn("还没有", action.reason)

    def test_final_answer_after_successful_read(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请读取 notes.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[
                Observation(
                    tool_name="read_file",
                    args={"path": "notes.md"},
                    result=ToolResult(success=True, content="# 示例笔记\n这是一个 Agent demo。"),
                )
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertIn("示例笔记", action.message or "")

    def test_final_answer_after_failed_read(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请读取 missing.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[
                Observation(
                    tool_name="read_file",
                    args={"path": "missing.md"},
                    result=ToolResult(success=False, error="file not found: missing.md"),
                )
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("读取文件失败", action.message or "")

    def test_lists_workspace_when_no_file_path_is_named(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请总结一下",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "list_dir")
        self.assertEqual(action.args, {"path": "."})

    def test_cannot_decide_without_file_path_when_list_dir_unavailable(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请总结一下",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("无法判断", action.message or "")

    def test_reads_markdown_file_after_successful_listing(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请总结一下",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
            ],
            observations=[
                Observation(
                    tool_name="list_dir",
                    args={"path": "."},
                    result=ToolResult(
                        success=True,
                        metadata={
                            "entries": [
                                {"type": "file", "path": "architecture.md"},
                                {"type": "file", "path": "notes.md"},
                                {"type": "directory", "path": "docs"},
                            ]
                        },
                    ),
                )
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "read_file")
        self.assertEqual(action.args, {"path": "architecture.md"})

    def test_prefers_relevant_markdown_file_after_successful_listing(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请总结这个 demo 的使用方式",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
            ],
            observations=[
                Observation(
                    tool_name="list_dir",
                    args={"path": "."},
                    result=ToolResult(
                        success=True,
                        metadata={
                            "entries": [
                                {"type": "file", "path": "architecture.md"},
                                {"type": "file", "path": "notes.md"},
                                {"type": "file", "path": "project.md"},
                                {"type": "file", "path": "usage.md"},
                            ]
                        },
                    ),
                )
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "read_file")
        self.assertEqual(action.args, {"path": "usage.md"})

    def test_final_answer_after_multiple_successful_reads(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请总结一下",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
            ],
            observations=[
                Observation(
                    tool_name="list_dir",
                    args={"path": "."},
                    result=ToolResult(
                        success=True,
                        metadata={
                            "entries": [
                                {"type": "file", "path": "architecture.md"},
                                {"type": "file", "path": "project.md"},
                            ]
                        },
                    ),
                ),
                Observation(
                    tool_name="read_file",
                    args={"path": "architecture.md"},
                    result=ToolResult(success=True, content="# 架构\nAgent Loop。"),
                ),
                Observation(
                    tool_name="read_file",
                    args={"path": "project.md"},
                    result=ToolResult(success=True, content="# 项目\n最小演示。"),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertIn("architecture.md", action.message or "")
        self.assertIn("project.md", action.message or "")

    def test_explicit_markdown_paths_are_capped_before_final_answer(self) -> None:
        from min_agent.fake_llm import FakeLLM, MAX_FAKE_READS
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        named_paths = ["a.md", "b.md", "c.md", "d.md"]
        context = AgentContext(
            user_goal=f"请总结 {' '.join(named_paths)}",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[
                Observation(
                    tool_name="read_file",
                    args={"path": target_path},
                    result=ToolResult(success=True, content=f"# {target_path}\n内容"),
                )
                for target_path in named_paths[:MAX_FAKE_READS]
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        for target_path in named_paths[:MAX_FAKE_READS]:
            self.assertIn(target_path, action.message or "")
        self.assertNotIn(named_paths[MAX_FAKE_READS], action.message or "")

    def test_fails_when_read_file_unavailable_after_listing(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请总结一下",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="list_dir", description="List directory")],
            observations=[
                Observation(
                    tool_name="list_dir",
                    args={"path": "."},
                    result=ToolResult(
                        success=True,
                        metadata={"entries": [{"type": "file", "path": "notes.md"}]},
                    ),
                )
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIsNone(action.tool_name)


    def test_requests_write_file_when_goal_asks_to_generate_summary_md(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请阅读这个工作区里的资料，并生成 summary.md",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file"),
            ],
            observations=[
                Observation(
                    tool_name="list_dir",
                    args={"path": "."},
                    result=ToolResult(
                        success=True,
                        metadata={
                            "entries": [
                                {"type": "file", "path": "usage.md"},
                                {"type": "file", "path": "project.md"},
                            ]
                        },
                    ),
                ),
                Observation(
                    tool_name="read_file",
                    args={"path": "usage.md"},
                    result=ToolResult(success=True, content="# 使用方式\nCLI 启动。"),
                ),
                Observation(
                    tool_name="read_file",
                    args={"path": "project.md"},
                    result=ToolResult(success=True, content="# 项目概览\n最小 Agent。"),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "write_file")
        self.assertEqual(action.args["path"], "summary.md")
        self.assertEqual(action.args.get("mode"), "create")
        self.assertIn("# Summary", action.args.get("content", ""))
        self.assertIn("usage.md", action.args.get("content", ""))
        self.assertIn("project.md", action.args.get("content", ""))

    def test_write_goal_without_source_files_lists_workspace_first(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请阅读这个工作区里的资料，并生成 summary.md",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file"),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "list_dir")
        self.assertEqual(action.args, {"path": "."})

    def test_write_goal_after_listing_reads_source_files_not_output_file(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请阅读这个工作区里的资料，并生成 summary.md",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file"),
            ],
            observations=[
                Observation(
                    tool_name="list_dir",
                    args={"path": "."},
                    result=ToolResult(
                        success=True,
                        metadata={
                            "entries": [
                                {"type": "file", "path": "usage.md"},
                                {"type": "file", "path": "project.md"},
                            ]
                        },
                    ),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "read_file")
        self.assertIn(action.args["path"], {"usage.md", "project.md"})
        self.assertNotEqual(action.args["path"], "summary.md")

    def test_write_goal_reads_remaining_source_files_before_write(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请阅读这个工作区里的资料，并生成 summary.md",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file"),
            ],
            observations=[
                Observation(
                    tool_name="list_dir",
                    args={"path": "."},
                    result=ToolResult(
                        success=True,
                        metadata={
                            "entries": [
                                {"type": "file", "path": "usage.md"},
                                {"type": "file", "path": "project.md"},
                            ]
                        },
                    ),
                ),
                Observation(
                    tool_name="read_file",
                    args={"path": "project.md"},
                    result=ToolResult(success=True, content="# 项目概览\n最小 Agent。"),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "read_file")
        self.assertEqual(action.args["path"], "usage.md")

    def test_requests_write_file_for_report_md_after_reading_sources(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请读取项目资料并写入 report.md",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file"),
            ],
            observations=[
                Observation(
                    tool_name="read_file",
                    args={"path": "project.md"},
                    result=ToolResult(success=True, content="# 项目概览\n最小 Agent。"),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "write_file")
        self.assertEqual(action.args["path"], "report.md")
        self.assertIn("project.md", action.args.get("content", ""))

    def test_final_answer_after_successful_write(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请生成 summary.md",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file"),
            ],
            observations=[
                Observation(
                    tool_name="read_file",
                    args={"path": "summary.md"},
                    result=ToolResult(success=True, content="# 示例\nhello."),
                ),
                Observation(
                    tool_name="write_file",
                    args={"path": "summary.md", "mode": "create"},
                    result=ToolResult(success=True, content="wrote file: summary.md"),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertTrue(action.success)
        self.assertIn("已生成 summary.md", action.message or "")

    def test_final_answer_after_permission_rejected(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请生成 summary.md",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file"),
            ],
            observations=[
                Observation(
                    tool_name="read_file",
                    args={"path": "summary.md"},
                    result=ToolResult(success=True, content="# 示例\nhello."),
                ),
                Observation(
                    tool_name="write_file",
                    args={"path": "summary.md", "mode": "create"},
                    result=ToolResult(
                        success=False,
                        error="permission denied by user",
                        metadata={"permission": "rejected"},
                    ),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("拒绝了写文件权限", action.message or "")

    # ---- V0.7: current-time command routing ----

    def test_chinese_time_goal_requests_run_command(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "run_command")
        self.assertEqual(action.args, {"command_id": "get_current_time"})

    def test_english_time_goal_requests_run_command(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="what time is it now?",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "run_command")
        self.assertEqual(action.args, {"command_id": "get_current_time"})

    def test_current_time_keyword_triggers_run_command(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="当前时间",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "run_command")

    def test_successful_time_observation_produces_final_answer(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
            ],
            observations=[
                Observation(
                    tool_name="run_command",
                    args={"command_id": "get_current_time"},
                    result=ToolResult(
                        success=True,
                        content="2026-07-03 10:30:21 CST",
                        metadata={"exit_code": 0},
                    ),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertTrue(action.success)
        self.assertIn("2026-07-03 10:30:21", action.message or "")

    def test_permission_rejected_time_produces_failed_final_answer(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
            ],
            observations=[
                Observation(
                    tool_name="run_command",
                    args={"command_id": "get_current_time"},
                    result=ToolResult(
                        success=False,
                        error="permission denied by user",
                        metadata={"permission": "rejected"},
                    ),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("未获授权", action.message or "")

    def test_command_timeout_produces_failed_final_answer(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
            ],
            observations=[
                Observation(
                    tool_name="run_command",
                    args={"command_id": "get_current_time"},
                    result=ToolResult(
                        success=False,
                        error="command_timeout",
                        metadata={"timed_out": True},
                    ),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)

    def test_run_command_unavailable_produces_failed_final_answer(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="list_dir", description="List directory"),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("实时", action.message or "")

    def test_time_goal_falls_back_to_file_discovery_when_no_time_keyword(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请总结一下",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
            ],
            observations=[],
        )

        action = llm.decide(context)

        # Should fall through to existing file-discovery logic
        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "list_dir")

    def test_no_write_file_when_write_tool_unavailable(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="请生成 summary.md",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[
                Observation(
                    tool_name="read_file",
                    args={"path": "summary.md"},
                    result=ToolResult(success=True, content="hello"),
                ),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("write_file", action.message or "")


if __name__ == "__main__":
    unittest.main()


# ===== V0.8 新增测试 =====


class FakeLLMV08ClassificationTest(unittest.TestCase):
    def test_core_composite_goal_creates_four_task_plan(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "create_plan")
        self.assertEqual(len(action.tasks), 4)

        # 验证任务标题是用户可理解的子目标，不是工具名
        titles = [t.title for t in action.tasks]
        self.assertIn("查看项目文件", titles)
        self.assertIn("读取并整理资料", titles)
        self.assertIn("获取当前时间", titles)
        self.assertIn("生成并写入摘要", titles)

        # 验证 task_id 顺序
        task_ids = [t.task_id for t in action.tasks]
        self.assertEqual(task_ids, ["task-1", "task-2", "task-3", "task-4"])

    def test_simple_time_query_still_returns_run_command(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "run_command")

    def test_simple_summary_goal_still_follows_v07_file_discovery(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="总结整个 workspace。",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
            ],
            observations=[],
        )

        action = llm.decide(context)

        # 不生成单任务计划，沿用 V0.7 文件发现
        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "list_dir")

    def test_multiple_tool_calls_alone_do_not_trigger_planning(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, ToolResult, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="读取 notes.md 和 architecture.md 并写一个 summary.md",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
            ],
            observations=[],
        )

        action = llm.decide(context)

        # 没有时间意图 → 不是复合目标
        self.assertNotEqual(action.kind, "create_plan")

    def test_boundary_read_then_write_without_time(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="看看 project.md 里有没有提到时间，写到 notes.md。",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
            ],
            observations=[],
        )

        action = llm.decide(context)

        # "时间"只是内容关键词，不是"获取当前时间"的意图 → 不是复合目标
        self.assertNotEqual(action.kind, "create_plan")

    def test_boundary_read_specific_file_with_time_keyword_in_content(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal='读取 workspace 里的 notes.md，并把包含"当前时间"的句子写到 summary.md。',
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
            ],
            observations=[],
        )

        action = llm.decide(context)
        # "当前时间"在引号中是内容匹配目标，不是获取系统时间的意图
        self.assertNotEqual(action.kind, "create_plan")

    def test_boundary_time_and_write_without_project_reading(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = FakeLLM()
        context = AgentContext(
            user_goal="获取当前时间并写到 summary.md，不需要阅读项目资料。",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
            ],
            observations=[],
        )

        action = llm.decide(context)
        # 没有项目/workspace 阅读意图 → 不是复合目标
        self.assertNotEqual(action.kind, "create_plan")


class FakeLLMV08PerTaskDecisionTest(unittest.TestCase):
    def test_task1_uses_list_dir_then_complete(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, TaskSnapshot, ToolResult, ToolSpec

        llm = FakeLLM()
        plan = [
            TaskSnapshot("task-1", "查看项目文件", "获得文件列表", "running"),
            TaskSnapshot("task-2", "读取并整理资料", "成功读取", "pending"),
            TaskSnapshot("task-3", "获取当前时间", "成功获取时间", "pending"),
            TaskSnapshot("task-4", "生成并写入摘要", "成功创建文件", "pending"),
        ]
        context = AgentContext(
            user_goal="阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
            ],
            observations=[],
            task_plan=plan,
            current_task_id="task-1",
        )

        action = llm.decide(context)
        # task-1: 第一步是 list_dir
        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "list_dir")

    def test_task1_completes_after_successful_listing(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, TaskSnapshot, ToolResult, ToolSpec

        llm = FakeLLM()
        plan = [
            TaskSnapshot("task-1", "查看项目文件", "获得文件列表", "running"),
            TaskSnapshot("task-2", "读取并整理资料", "成功读取", "pending"),
            TaskSnapshot("task-3", "获取当前时间", "成功获取时间", "pending"),
            TaskSnapshot("task-4", "生成并写入摘要", "成功创建文件", "pending"),
        ]
        context = AgentContext(
            user_goal="阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
            ],
            observations=[
                Observation(
                    tool_name="list_dir",
                    args={"path": "."},
                    result=ToolResult(
                        success=True,
                        metadata={
                            "entries": [
                                {"type": "file", "path": "project.md"},
                                {"type": "file", "path": "architecture.md"},
                            ]
                        },
                    ),
                ),
            ],
            task_plan=plan,
            current_task_id="task-1",
        )

        action = llm.decide(context)
        # task-1: list_dir 成功后完成
        self.assertEqual(action.kind, "complete_task")
        self.assertEqual(action.task_id, "task-1")
        self.assertEqual(action.evidence_observation_indexes, [1])

    def test_task3_uses_run_command_then_complete(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, TaskSnapshot, ToolResult, ToolSpec

        llm = FakeLLM()
        plan = [
            TaskSnapshot("task-1", "查看项目文件", "获得文件列表", "completed"),
            TaskSnapshot("task-2", "读取并整理资料", "成功读取", "completed"),
            TaskSnapshot("task-3", "获取当前时间", "成功获取时间", "running"),
            TaskSnapshot("task-4", "生成并写入摘要", "成功创建文件", "pending"),
        ]
        context = AgentContext(
            user_goal="阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
            ],
            observations=[],
            task_plan=plan,
            current_task_id="task-3",
        )

        action = llm.decide(context)
        # task-3: 第一步是 run_command
        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "run_command")
        self.assertEqual(action.args, {"command_id": "get_current_time"})

    def test_task3_completes_after_time_observation(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, Observation, TaskSnapshot, ToolResult, ToolSpec

        llm = FakeLLM()
        plan = [
            TaskSnapshot("task-1", "查看项目文件", "获得文件列表", "completed"),
            TaskSnapshot("task-2", "读取并整理资料", "成功读取", "completed"),
            TaskSnapshot("task-3", "获取当前时间", "成功获取时间", "running"),
            TaskSnapshot("task-4", "生成并写入摘要", "成功创建文件", "pending"),
        ]
        context = AgentContext(
            user_goal="阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
            ],
            observations=[
                Observation(
                    tool_name="run_command",
                    args={"command_id": "get_current_time"},
                    result=ToolResult(success=True, content="2026-07-07 10:30:00 CST"),
                ),
            ],
            task_plan=plan,
            current_task_id="task-3",
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "complete_task")
        self.assertEqual(action.task_id, "task-3")

    def test_task4_writes_summary_from_inherited_artifacts(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, TaskArtifact, TaskSnapshot, ToolSpec

        llm = FakeLLM()
        self.assertFalse(hasattr(llm, "_composite_read_contents"))
        self.assertFalse(hasattr(llm, "_composite_time_result"))

        plan = [
            TaskSnapshot("task-1", "查看项目文件", "获得文件列表", "completed"),
            TaskSnapshot("task-2", "读取并整理资料", "成功读取", "completed"),
            TaskSnapshot("task-3", "获取当前时间", "成功获取时间", "completed"),
            TaskSnapshot("task-4", "生成并写入摘要", "成功创建文件", "running"),
        ]
        context = AgentContext(
            user_goal="阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
            ],
            observations=[],
            task_plan=plan,
            current_task_id="task-4",
            inherited_task_artifacts=[
                TaskArtifact("task-2", "项目资料摘要", "## project.md\n# 项目 Min Agent", [1], 10, "available"),
                TaskArtifact("task-3", "当前本地时间", "2026-07-07 10:30:00 CST", [1], 20, "available"),
            ],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "write_file")
        self.assertEqual(action.args["path"], "summary.md")
        self.assertEqual(action.args.get("mode"), "create")
        content = action.args.get("content", "")
        self.assertIn("2026-07-07 10:30:00 CST", content)
        self.assertIn("project.md", content)

    def test_all_completed_returns_final_answer(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, TaskSnapshot, ToolSpec

        llm = FakeLLM()
        plan = [
            TaskSnapshot("task-1", "查看项目文件", "done", "completed"),
            TaskSnapshot("task-2", "读取并整理资料", "done", "completed"),
            TaskSnapshot("task-3", "获取当前时间", "done", "completed"),
            TaskSnapshot("task-4", "生成并写入摘要", "done", "completed"),
        ]
        context = AgentContext(
            user_goal="阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[],
            task_plan=plan,
            current_task_id=None,
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertTrue(action.success)
        self.assertIn("summary.md", action.message or "")

    def test_planned_goal_never_returns_create_plan_again(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.types import AgentContext, TaskSnapshot, ToolSpec

        llm = FakeLLM()
        plan = [
            TaskSnapshot("task-1", "查看项目文件", "done", "running"),
            TaskSnapshot("task-2", "读取并整理资料", "done", "pending"),
        ]
        context = AgentContext(
            user_goal="阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List directory"),
            ],
            observations=[],
            task_plan=plan,
            current_task_id="task-1",
        )

        action = llm.decide(context)

        # 计划已存在，不再返回 create_plan
        self.assertNotEqual(action.kind, "create_plan")
