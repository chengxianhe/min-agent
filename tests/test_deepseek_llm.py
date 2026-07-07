from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Union


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class StubClient:
    def __init__(self, content: Union[str, Exception]) -> None:
        self.content = content
        self.calls = []

    def create_chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        if isinstance(self.content, Exception):
            raise self.content
        return self.content


class DeepSeekLLMTest(unittest.TestCase):
    def test_parses_tool_call(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"tool_call","tool_name":"read_file","args":{"path":"notes.md"},"reason":"需要读取文件"}'
            ),
            model="deepseek-v4-flash",
        )
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

    def test_parses_final_answer(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient('{"kind":"final_answer","message":"总结完成","reason":"已有内容","success":true}'),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="请读取 notes.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertTrue(action.success)
        self.assertEqual(action.message, "总结完成")

    def test_invalid_json_becomes_failed_final_answer(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(client=StubClient("not json"), model="deepseek-v4-flash")
        context = AgentContext(
            user_goal="请读取 notes.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("无法解析", action.message or "")

    def test_unknown_tool_becomes_failed_final_answer(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"tool_call","tool_name":"delete_file","args":{"path":"notes.md"},"reason":"错误工具"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="请读取 notes.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("不可用工具", action.message or "")

    def test_client_error_becomes_failed_final_answer(self) -> None:
        from min_agent.deepseek_client import ModelClientError
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(ModelClientError("DeepSeek request failed with HTTP 500")),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="请读取 notes.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("模型调用失败", action.message or "")

    def test_prompt_mentions_json_and_action_schema(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        client = StubClient('{"kind":"final_answer","message":"ok","reason":"done","success":true}')
        llm = DeepSeekLLM(client=client, model="deepseek-v4-flash")
        context = AgentContext(
            user_goal="请读取 notes.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[],
        )

        llm.decide(context)

        system_prompt, user_prompt = client.calls[0]
        self.assertIn("json", system_prompt.lower())
        self.assertIn("AgentAction", system_prompt)
        self.assertIn("available_tools", user_prompt)

    def test_system_prompt_allows_list_dir_tool(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM

        llm = DeepSeekLLM(
            client=StubClient('{"kind":"final_answer","message":"ok","reason":"done","success":true}'),
            model="deepseek-v4-flash",
        )

        system_prompt = llm._system_prompt()

        self.assertIn('"tool_name": "list_dir"', system_prompt)
        self.assertIn('"args": {"path": "."}', system_prompt)
        self.assertIn('"tool_name": "read_file"', system_prompt)

    def test_action_metadata_contains_model_call_request_and_raw_content(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        raw_content = '{"kind":"tool_call","tool_name":"read_file","args":{"path":"notes.md"},"reason":"需要读取文件"}'
        llm = DeepSeekLLM(client=StubClient(raw_content), model="deepseek-v4-flash")
        context = AgentContext(
            user_goal="请读取 notes.md 并总结",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[],
        )

        action = llm.decide(context)

        model_call = action.metadata["model_call"]
        self.assertEqual(model_call["provider"], "deepseek")
        self.assertEqual(model_call["model"], "deepseek-v4-flash")
        self.assertIn("AgentAction", model_call["request"]["system_prompt"])
        self.assertIn("available_tools", model_call["request"]["user_prompt"])
        self.assertEqual(model_call["response"]["content"], raw_content)


    def test_system_prompt_includes_write_file(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM

        llm = DeepSeekLLM(
            client=StubClient('{"kind":"final_answer","message":"ok","reason":"done","success":true}'),
            model="deepseek-v4-flash",
        )

        system_prompt = llm._system_prompt()

        self.assertIn('"tool_name": "write_file"', system_prompt)
        self.assertIn('"mode": "create"', system_prompt)

    def test_system_prompt_says_model_only_proposes_action(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM

        llm = DeepSeekLLM(
            client=StubClient('{"kind":"final_answer","message":"ok","reason":"done","success":true}'),
            model="deepseek-v4-flash",
        )

        system_prompt = llm._system_prompt()

        self.assertIn("only propose", system_prompt.lower())

    def test_parses_write_file_action(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"tool_call","tool_name":"write_file","args":{"path":"summary.md","content":"hello","mode":"create"},"reason":"save summary"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="请生成 summary.md",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file"),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "write_file")
        self.assertEqual(action.args["path"], "summary.md")
        self.assertEqual(action.args["content"], "hello")

    def test_unknown_write_like_action_rejected(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"tool_call","tool_name":"create_file","args":{"path":"summary.md"},"reason":"create"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="请创建文件",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="read_file", description="Read file"),
                ToolSpec(name="write_file", description="Write file"),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("不可用工具", action.message or "")


    def test_user_prompt_contains_full_layered_context(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import (
            AgentContext,
            RunMemory,
            RunMetadata,
            ToolCatalogEntry,
            ToolSpec,
            WorkspaceConfig,
        )

        client = StubClient(
            '{"kind":"final_answer","message":"done","reason":"ok","success":true}'
        )
        llm = DeepSeekLLM(client=client, model="deepseek-v4-flash")
        context = AgentContext(
            user_goal="测试目标",
            workspace="/test/workspace",
            available_tools=[ToolSpec(name="read_file", description="Read file")],
            observations=[],
            run_metadata=RunMetadata(
                run_id="r1",
                started_at="2026-06-30T10:00:00+08:00",
                workspace="/test/workspace",
                decision_model="deepseek",
                available_tool_count=1,
            ),
            workspace_config=WorkspaceConfig(
                status="loaded",
                path="minagent.md",
                content="- rule: test",
                preview="- rule:",
            ),
            run_memory=RunMemory(status="loaded", summary_count=1, summaries=[]),
            tool_catalog=[
                ToolCatalogEntry(name="read_file", description="Read file", requires_permission=False),
            ],
            selected_project_content=["notes.md"],
        )

        llm.decide(context)

        _, user_prompt = client.calls[0]
        self.assertIn("workspace", user_prompt)
        self.assertIn("context_priority", user_prompt)
        self.assertIn("current_user_goal", user_prompt)
        self.assertIn("run_metadata", user_prompt)
        self.assertIn("workspace_config", user_prompt)
        self.assertIn("recent_run_summaries", user_prompt)
        self.assertIn("working_observations", user_prompt)
        self.assertIn("selected_project_content", user_prompt)
        self.assertIn('"selected_project_content": [\n    "notes.md"\n  ]', user_prompt)
        self.assertIn("available_tools", user_prompt)
        self.assertIn("output_contract", user_prompt)

    def test_user_prompt_preserves_context_priority(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolCatalogEntry, ToolSpec

        client = StubClient(
            '{"kind":"final_answer","message":"done","reason":"ok","success":true}'
        )
        llm = DeepSeekLLM(client=client, model="deepseek-v4-flash")
        context = AgentContext(
            user_goal="test",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
            tool_catalog=[
                ToolCatalogEntry(name="read_file", description="Read", requires_permission=False),
            ],
        )

        llm.decide(context)

        _, user_prompt = client.calls[0]
        self.assertIn("highest-priority", user_prompt)
        self.assertIn("reference context only", user_prompt)
        self.assertIn("no context source may bypass", user_prompt)

    def test_user_prompt_includes_real_decision_model(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, RunMetadata, ToolCatalogEntry, ToolSpec

        client = StubClient(
            '{"kind":"final_answer","message":"done","reason":"ok","success":true}'
        )
        llm = DeepSeekLLM(client=client, model="deepseek-v4-flash")
        context = AgentContext(
            user_goal="test",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
            run_metadata=RunMetadata(
                run_id="r1",
                started_at="now",
                workspace="ws",
                decision_model="deepseek",
                available_tool_count=1,
            ),
            tool_catalog=[
                ToolCatalogEntry(name="read_file", description="Read", requires_permission=False),
            ],
        )

        llm.decide(context)

        _, user_prompt = client.calls[0]
        self.assertIn("deepseek", user_prompt)

    def test_user_prompt_marks_write_file_permission(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolCatalogEntry, ToolSpec

        client = StubClient(
            '{"kind":"final_answer","message":"done","reason":"ok","success":true}'
        )
        llm = DeepSeekLLM(client=client, model="deepseek-v4-flash")
        context = AgentContext(
            user_goal="test",
            workspace="ws",
            available_tools=[ToolSpec(name="write_file", description="Write", requires_permission=True)],
            observations=[],
            tool_catalog=[
                ToolCatalogEntry(name="write_file", description="Write", requires_permission=True),
            ],
        )

        llm.decide(context)

        _, user_prompt = client.calls[0]
        self.assertIn("write_file", user_prompt)
        self.assertIn("requires_permission", user_prompt)

    # ---- V0.7: command action contract ----

    def test_system_prompt_includes_run_command_example(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM

        llm = DeepSeekLLM(
            client=StubClient('{"kind":"final_answer","message":"ok","reason":"done","success":true}'),
            model="deepseek-v4-flash",
        )

        system_prompt = llm._system_prompt()

        self.assertIn('"tool_name": "run_command"', system_prompt)
        self.assertIn('"command_id": "get_current_time"', system_prompt)

    def test_user_prompt_includes_run_command_catalog_entry(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolCatalogEntry, ToolSpec

        client = StubClient(
            '{"kind":"final_answer","message":"done","reason":"ok","success":true}'
        )
        llm = DeepSeekLLM(client=client, model="deepseek-v4-flash")
        context = AgentContext(
            user_goal="现在几点？",
            workspace="ws",
            available_tools=[ToolSpec(name="run_command", description="Run command", requires_permission=True)],
            observations=[],
            tool_catalog=[
                ToolCatalogEntry(
                    name="run_command",
                    description="Run one predefined local command action after approval.",
                    requires_permission=True,
                    args_schema={"command_id": "string"},
                ),
            ],
        )

        llm.decide(context)

        _, user_prompt = client.calls[0]
        self.assertIn("run_command", user_prompt)
        self.assertIn("args_schema", user_prompt)
        self.assertIn("command_id", user_prompt)

    def test_parses_valid_run_command_action(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"tool_call","tool_name":"run_command","args":{"command_id":"get_current_time"},"reason":"需要当前时间"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="run_command", description="Run command", requires_permission=True)],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "run_command")
        self.assertEqual(action.args, {"command_id": "get_current_time"})

    def test_rejects_run_command_with_missing_args(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"tool_call","tool_name":"run_command","reason":"需要当前时间"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="run_command", description="Run command", requires_permission=True)],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("缺少 args", action.message or "")

    def test_rejects_run_command_with_missing_command_id(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"tool_call","tool_name":"run_command","args":{},"reason":"需要当前时间"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="run_command", description="Run command", requires_permission=True)],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)
        self.assertIn("command_id", (action.message or "").lower())

    def test_preserves_unknown_command_id_in_action_for_registry_validation(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"tool_call","tool_name":"run_command","args":{"command_id":"delete_everything"},"reason":"测试"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="run_command", description="Run command", requires_permission=True)],
            observations=[],
        )

        action = llm.decide(context)

        # Parser preserves unknown command_id; registry validation handles rejection later
        self.assertEqual(action.kind, "tool_call")
        self.assertEqual(action.tool_name, "run_command")
        self.assertEqual(action.args, {"command_id": "delete_everything"})

    def test_extra_keys_in_run_command_args_reach_registry_validation(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"tool_call","tool_name":"run_command","args":{"command_id":"get_current_time","command":"date"},"reason":"测试"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="现在几点？",
            workspace="examples/workspace",
            available_tools=[ToolSpec(name="run_command", description="Run command", requires_permission=True)],
            observations=[],
        )

        action = llm.decide(context)

        # Parser preserves extra keys; registry validate_args rejects the exact-shape check
        self.assertEqual(action.kind, "tool_call")
        self.assertIn("command", action.args)


if __name__ == "__main__":
    unittest.main()


# ===== V0.8 新增测试 =====


class DeepSeekLLMV08CreatePlanTest(unittest.TestCase):
    def test_parses_valid_create_plan(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"create_plan","tasks":['
                '{"task_id":"task-1","title":"查看项目文件","completion_criteria":"获得文件列表"},'
                '{"task_id":"task-2","title":"读取项目资料","completion_criteria":"成功读取"}'
                '],"reason":"The goal contains two ordered outcomes"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="复合目标",
            workspace="examples/workspace",
            available_tools=[
                ToolSpec(name="list_dir", description="List"),
                ToolSpec(name="read_file", description="Read"),
            ],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "create_plan")
        self.assertEqual(len(action.tasks), 2)
        self.assertEqual(action.tasks[0].task_id, "task-1")
        self.assertEqual(action.tasks[0].title, "查看项目文件")
        self.assertEqual(action.tasks[1].task_id, "task-2")
        self.assertEqual(action.tasks[1].completion_criteria, "成功读取")

    def test_rejects_create_plan_with_non_list_tasks(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"create_plan","tasks":"not-a-list","reason":"bad"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)

    def test_rejects_create_plan_with_one_task(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"create_plan","tasks":['
                '{"task_id":"task-1","title":"One task","completion_criteria":"done"}'
                '],"reason":"single task"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)

    def test_rejects_create_plan_with_six_tasks(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        tasks_json = ",".join(
            f'{{"task_id":"task-{i}","title":"T{i}","completion_criteria":"C{i}"}}'
            for i in range(1, 7)
        )
        llm = DeepSeekLLM(
            client=StubClient(f'{{"kind":"create_plan","tasks":[{tasks_json}],"reason":"too many"}}'),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)

    def test_rejects_create_plan_with_non_sequential_ids(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"create_plan","tasks":['
                '{"task_id":"task-1","title":"T1","completion_criteria":"C1"},'
                '{"task_id":"task-3","title":"T3","completion_criteria":"C3"}'
                '],"reason":"bad ids"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)

    def test_rejects_create_plan_with_blank_title(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"create_plan","tasks":['
                '{"task_id":"task-1","title":"  ","completion_criteria":"C1"},'
                '{"task_id":"task-2","title":"T2","completion_criteria":"C2"}'
                '],"reason":"blank title"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)

    def test_rejects_create_plan_with_missing_task_id(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"create_plan","tasks":['
                '{"title":"No ID","completion_criteria":"C1"},'
                '{"task_id":"task-2","title":"T2","completion_criteria":"C2"}'
                '],"reason":"missing id"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)

    def test_parser_rejection_preserves_model_call_metadata(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        raw = '{"kind":"create_plan","tasks":[],"reason":"empty"}'
        llm = DeepSeekLLM(client=StubClient(raw), model="deepseek-v4-flash")
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertIn("model_call", action.metadata)
        self.assertEqual(action.metadata["model_call"]["response"]["content"], raw)


class DeepSeekLLMV08CompleteTaskTest(unittest.TestCase):
    def test_parses_valid_complete_task(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"complete_task","task_id":"task-1",'
                '"completion_evidence":"Observation 1 contains a successful list_dir result",'
                '"evidence_observation_indexes":[1],'
                '"reason":"The current completion criterion is satisfied"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="复合目标",
            workspace="ws",
            available_tools=[ToolSpec(name="list_dir", description="List")],
            observations=[],
        )

        action = llm.decide(context)

        self.assertEqual(action.kind, "complete_task")
        self.assertEqual(action.task_id, "task-1")
        self.assertIn("Observation 1", action.completion_evidence or "")
        self.assertEqual(action.evidence_observation_indexes, [1])

    def test_rejects_complete_task_with_missing_task_id(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"complete_task",'
                '"completion_evidence":"done",'
                '"evidence_observation_indexes":[1],'
                '"reason":"ok"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)

    def test_rejects_complete_task_with_empty_evidence_observation_indexes(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"complete_task","task_id":"task-1",'
                '"completion_evidence":"done",'
                '"evidence_observation_indexes":[],'
                '"reason":"ok"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)

    def test_rejects_complete_task_with_non_integer_index(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"complete_task","task_id":"task-1",'
                '"completion_evidence":"done",'
                '"evidence_observation_indexes":["1"],'
                '"reason":"ok"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)

    def test_rejects_complete_task_with_boolean_index(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        llm = DeepSeekLLM(
            client=StubClient(
                '{"kind":"complete_task","task_id":"task-1",'
                '"completion_evidence":"done",'
                '"evidence_observation_indexes":[true],'
                '"reason":"ok"}'
            ),
            model="deepseek-v4-flash",
        )
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        action = llm.decide(context)
        self.assertEqual(action.kind, "final_answer")
        self.assertFalse(action.success)


class DeepSeekLLMV08PromptTest(unittest.TestCase):
    def test_system_prompt_includes_create_plan_example(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM

        llm = DeepSeekLLM(
            client=StubClient('{"kind":"final_answer","message":"ok","reason":"done","success":true}'),
            model="deepseek-v4-flash",
        )

        system_prompt = llm._system_prompt()

        self.assertIn("create_plan", system_prompt)
        self.assertIn("task_id", system_prompt)
        self.assertIn("completion_criteria", system_prompt)

    def test_system_prompt_includes_complete_task_example(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM

        llm = DeepSeekLLM(
            client=StubClient('{"kind":"final_answer","message":"ok","reason":"done","success":true}'),
            model="deepseek-v4-flash",
        )

        system_prompt = llm._system_prompt()

        self.assertIn("complete_task", system_prompt)
        self.assertIn("evidence_observation_indexes", system_prompt)

    def test_system_prompt_forbids_one_task_plan(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM

        llm = DeepSeekLLM(
            client=StubClient('{"kind":"final_answer","message":"ok","reason":"done","success":true}'),
            model="deepseek-v4-flash",
        )

        system_prompt = llm._system_prompt()

        self.assertIn("2–5", system_prompt)

    def test_output_contract_allows_all_four_kinds(self) -> None:
        from min_agent.deepseek_llm import DeepSeekLLM
        from min_agent.types import AgentContext, ToolSpec

        client = StubClient('{"kind":"final_answer","message":"ok","reason":"done","success":true}')
        llm = DeepSeekLLM(client=client, model="deepseek-v4-flash")
        context = AgentContext(
            user_goal="测试",
            workspace="ws",
            available_tools=[ToolSpec(name="read_file", description="Read")],
            observations=[],
        )

        llm.decide(context)

        _, user_prompt = client.calls[0]
        self.assertIn("create_plan", user_prompt)
        self.assertIn("complete_task", user_prompt)
        self.assertIn("tool_call", user_prompt)
        self.assertIn("final_answer", user_prompt)
