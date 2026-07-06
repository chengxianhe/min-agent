from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class PermissionFlowTest(unittest.TestCase):
    def test_permissioned_tool_not_executed_when_callback_rejects(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        tool_calls: list[dict] = []

        def handler(args: dict) -> ToolResult:
            tool_calls.append(args)
            return ToolResult(success=True, content="written")

        class WriteRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "write_file",
                        {"path": "summary.md", "content": "hello"},
                        "need to write summary",
                    )
                return AgentAction.final_answer("rejected", "user said no", success=False)

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
                handler,
            )
            recorder = TraceRecorder(user_goal="write summary.md", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=WriteRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: False,
            )

            result = loop.run("write summary.md")

        self.assertFalse(result.success)
        self.assertEqual(tool_calls, [])

    def test_permission_rejection_emits_permission_requested(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class WriteRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "write_file",
                        {"path": "summary.md", "content": "hello"},
                        "need to write summary",
                    )
                return AgentAction.final_answer("rejected", "user said no")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
                lambda args: ToolResult(success=True, content="written"),
            )
            recorder = TraceRecorder(user_goal="write summary.md", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=WriteRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: False,
            )

            loop.run("write summary.md")

        phases = [event.phase for event in recorder.history()]
        self.assertIn("permission_requested", phases)
        self.assertIn("permission_resolved", phases)

    def test_permission_rejection_emits_permission_resolved_with_approved_false(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class WriteRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "write_file",
                        {"path": "summary.md", "content": "hello"},
                        "need to write",
                    )
                return AgentAction.final_answer("ok", "done")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
                lambda args: ToolResult(success=True, content="written"),
            )
            recorder = TraceRecorder(user_goal="write summary.md", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=WriteRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: False,
            )

            loop.run("write summary.md")

        resolved = [
            event for event in recorder.history() if event.phase == "permission_resolved"
        ]
        self.assertEqual(len(resolved), 1)
        self.assertFalse(resolved[0].output["approved"])

    def test_rejection_creates_observation_with_permission_rejected(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class WriteRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "write_file",
                        {"path": "summary.md", "content": "hello"},
                        "need to write",
                    )
                return AgentAction.final_answer("ok", "done")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
                lambda args: ToolResult(success=True, content="written"),
            )
            recorder = TraceRecorder(user_goal="write summary.md", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=WriteRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: False,
            )

            loop.run("write summary.md")

        observations = [
            event for event in recorder.history() if event.phase == "observation_added"
        ]
        self.assertEqual(len(observations), 1)
        obs = observations[0].output
        self.assertEqual(obs["tool_name"], "write_file")
        self.assertFalse(obs["result"]["success"])
        self.assertEqual(obs["result"]["metadata"]["permission"], "rejected")

    def test_approved_permission_executes_write_file(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class WriteRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "write_file",
                        {"path": "summary.md", "content": "hello"},
                        "need to write",
                    )
                return AgentAction.final_answer("wrote file", "done", success=True)

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
                lambda args: ToolResult(success=True, content="wrote file: summary.md"),
            )
            recorder = TraceRecorder(user_goal="write summary.md", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=WriteRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: True,
            )

            result = loop.run("write summary.md")

        self.assertTrue(result.success)
        self.assertIn("wrote file", result.message)

    def test_approved_permission_emits_permission_resolved_with_approved_true(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class WriteRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "write_file",
                        {"path": "summary.md", "content": "hello"},
                        "need to write",
                    )
                return AgentAction.final_answer("ok", "done")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
                lambda args: ToolResult(success=True, content="written"),
            )
            recorder = TraceRecorder(user_goal="write summary.md", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=WriteRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: True,
            )

            loop.run("write summary.md")

        resolved = [
            event for event in recorder.history() if event.phase == "permission_resolved"
        ]
        self.assertEqual(len(resolved), 1)
        self.assertTrue(resolved[0].output["approved"])

    def test_non_permission_tools_execute_without_callback(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class ReadRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "read_file",
                        {"path": "notes.md"},
                        "need to read file",
                    )
                return AgentAction.final_answer("done", "read complete")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "notes.md").write_text("content", encoding="utf-8")
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="read_file", description="Read file", requires_permission=False),
                lambda args: ToolResult(success=True, content="content"),
            )
            recorder = TraceRecorder(user_goal="read notes.md", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=ReadRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: False,
            )

            result = loop.run("read notes.md")

        self.assertTrue(result.success)
        permissions = [
            event for event in recorder.history() if event.phase == "permission_requested"
        ]
        self.assertEqual(permissions, [])

    def test_permission_preview_ignores_non_string_content_without_crashing(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.tools.workspace import write_file
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolSpec

        class InvalidWriteModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "write_file",
                        {"path": "summary.md", "content": 123},
                        "model returned invalid write content",
                    )
                return AgentAction.final_answer(
                    "write failed visibly",
                    "invalid content was observed",
                    success=False,
                )

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
                lambda args: write_file(workspace, args),
            )
            recorder = TraceRecorder(user_goal="write summary.md", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=InvalidWriteModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: True,
            )

            result = loop.run("write summary.md")

        self.assertFalse(result.success)
        permission_requests = [
            event for event in recorder.history() if event.phase == "permission_requested"
        ]
        self.assertEqual(permission_requests[0].input["preview"], "")
        tool_finished = [
            event for event in recorder.history() if event.phase == "tool_finished"
        ]
        self.assertEqual(tool_finished[0].status, "failed")
        self.assertIn("content must be a string", tool_finished[0].output["error"])

    # ---- V0.7: generic preflight and permission details ----

    def test_invalid_command_args_create_observation_without_permission_or_tool_started(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class TimeRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "run_command",
                        {"command_id": "delete_everything"},
                        "need current time",
                    )
                return AgentAction.final_answer("failed", "invalid command", success=False)

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
                lambda args: ToolResult(success=True, content="ok"),
                validator=lambda args: (
                    ToolResult(success=False, error="unknown_command_id")
                    if args.get("command_id") != "get_current_time"
                    else None
                ),
            )
            recorder = TraceRecorder(user_goal="现在几点？", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=TimeRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: True,
            )

            loop.run("现在几点？")

        phases = [event.phase for event in recorder.history()]
        self.assertIn("observation_added", phases)
        self.assertNotIn("permission_requested", phases)
        self.assertNotIn("tool_started", phases)

    def test_valid_permission_details_appear_in_permission_requested(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class TimeRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "run_command",
                        {"command_id": "get_current_time"},
                        "need current time",
                    )
                return AgentAction.final_answer("time is now", "got time")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
                lambda args: ToolResult(success=True, content="2026-07-03 10:30:21 CST"),
                validator=lambda args: None,
                permission_describer=lambda args: {
                    "command_id": "get_current_time",
                    "command": '/bin/date "+%Y-%m-%d %H:%M:%S %Z"',
                    "workspace": str(workspace),
                    "risk": "只读",
                },
            )
            recorder = TraceRecorder(user_goal="现在几点？", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=TimeRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: True,
            )

            loop.run("现在几点？")

        permission_requests = [
            event for event in recorder.history() if event.phase == "permission_requested"
        ]
        self.assertEqual(len(permission_requests), 1)
        details = permission_requests[0].input.get("details", {})
        self.assertEqual(details["command_id"], "get_current_time")

    def test_callback_receives_action_and_details(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        captured: list = []

        class TimeRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "run_command",
                        {"command_id": "get_current_time"},
                        "need current time",
                    )
                return AgentAction.final_answer("time is now", "got time")

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
                lambda args: ToolResult(success=True, content="2026-07-03 10:30:21 CST"),
                validator=lambda args: None,
                permission_describer=lambda args: {
                    "command_id": "get_current_time",
                    "command": '/bin/date "+%Y-%m-%d %H:%M:%S %Z"',
                },
            )
            recorder = TraceRecorder(user_goal="现在几点？", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=TimeRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda action, details: (
                    captured.append((action.tool_name, details.get("command_id")))
                    or True
                ),
            )

            loop.run("现在几点？")

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0], ("run_command", "get_current_time"))

    def test_rejected_call_does_not_emit_tool_started_for_run_command(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class TimeRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "run_command",
                        {"command_id": "get_current_time"},
                        "need current time",
                    )
                return AgentAction.final_answer("cannot get time", "rejected", success=False)

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="run_command", description="Run command", requires_permission=True),
                lambda args: ToolResult(success=True, content="time"),
                validator=lambda args: None,
            )
            recorder = TraceRecorder(user_goal="现在几点？", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=TimeRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: False,
            )

            loop.run("现在几点？")

        tool_started = [
            event for event in recorder.history() if event.phase == "tool_started"
        ]
        self.assertEqual(tool_started, [])

    def test_existing_write_file_approval_and_rejection_unchanged(self) -> None:
        from min_agent.agent_loop import AgentLoop
        from min_agent.context_builder import ContextBuilder
        from min_agent.tool_registry import ToolRegistry
        from min_agent.trace_recorder import TraceRecorder
        from min_agent.types import AgentAction, AgentContext, ToolResult, ToolSpec

        class WriteRequestModel:
            def decide(self, context: AgentContext) -> AgentAction:
                if not context.observations:
                    return AgentAction.tool_call(
                        "write_file",
                        {"path": "summary.md", "content": "hello"},
                        "need to write",
                    )
                return AgentAction.final_answer("wrote file", "done", success=True)

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            registry = ToolRegistry()
            registry.register(
                ToolSpec(name="write_file", description="Write file", requires_permission=True),
                lambda args: ToolResult(success=True, content="wrote file: summary.md"),
            )
            recorder = TraceRecorder(user_goal="write summary.md", workspace=str(workspace))
            loop = AgentLoop(
                context_builder=ContextBuilder(),
                llm=WriteRequestModel(),
                tools=registry,
                recorder=recorder,
                workspace=str(workspace),
                max_turns=3,
                step_delay_seconds=0,
                permission_callback=lambda _action, _details: True,
            )

            result = loop.run("write summary.md")

        self.assertTrue(result.success)
        self.assertIn("wrote file", result.message)


if __name__ == "__main__":
    unittest.main()
