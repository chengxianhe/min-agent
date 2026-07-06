from __future__ import annotations

import time
from collections.abc import Callable

from min_agent.context_builder import ContextBuilder
from min_agent.decision_model import DecisionModel
from min_agent.tool_registry import ToolRegistry
from min_agent.trace_recorder import TraceRecorder
from min_agent.types import AgentAction, AgentRunResult, Observation, ToolResult


def preview_text(value: str, limit: int = 200) -> str:
    return value if len(value) <= limit else value[:limit] + "..."


class AgentLoop:
    def __init__(
        self,
        context_builder: ContextBuilder,
        llm: DecisionModel,
        tools: ToolRegistry,
        recorder: TraceRecorder,
        workspace: str,
        max_turns: int = 8,
        step_delay_seconds: float = 0.4,
        permission_callback: Callable[[AgentAction, dict[str, Any]], bool] | None = None,
    ) -> None:
        self.context_builder = context_builder
        self.llm = llm
        self.tools = tools
        self.recorder = recorder
        self.workspace = workspace
        self.max_turns = max_turns
        self.step_delay_seconds = step_delay_seconds
        self.permission_callback = permission_callback or (lambda _action, _details: False)
        self.observations: list[Observation] = []
        self._selected_project_content: list[str] = []

    def run(self, user_goal: str) -> AgentRunResult:
        self.recorder.emit(
            phase="run_started",
            status="running",
            title="收到任务",
            reason="用户提交了一个目标",
            input={"user_goal": user_goal, "workspace": self.workspace},
        )

        for _turn in range(self.max_turns):
            self._pause()
            context = self.context_builder.build(
                user_goal=user_goal,
                workspace=self.workspace,
                available_tools=self.tools.list_specs(),
                observations=self.observations,
                selected_project_content=self._selected_project_content,
                run_id=self.recorder.run_id,
                started_at=self.recorder.started_at,
            )
            self.recorder.emit(
                phase="context_built",
                status="running",
                title="整理上下文",
                reason="准备用户目标、可用工具和已有观察结果",
                output=context.to_dict(),
            )

            self._pause()
            action = self.llm.decide(context)
            self.recorder.emit(
                phase="llm_decision",
                status="running",
                title="决定下一步",
                reason=action.reason,
                output=action.to_dict(),
            )

            if action.kind == "final_answer":
                message = action.message or ""
                status = "completed" if action.success else "failed"
                self.recorder.emit(
                    phase="final_answer",
                    status=status,
                    title="生成最终回答",
                    reason=action.reason,
                    output={"message": message},
                )
                self.recorder.emit(
                    phase="run_completed" if status == "completed" else "run_failed",
                    status=status,
                    title="任务完成" if status == "completed" else "任务失败",
                    output={"message": message},
                )
                return AgentRunResult(message=message, success=action.success)

            if action.tool_name is None:
                return self._fail("模型返回了工具调用，但没有提供工具名称")

            # --- V0.7: generic preflight validation ---
            spec = self.tools.get_spec(action.tool_name)
            validation_error = self.tools.validate_call(action.tool_name, action.args)
            if validation_error is not None:
                observation = Observation(
                    tool_name=action.tool_name,
                    args=action.args,
                    result=validation_error,
                )
                self.observations.append(observation)
                self.recorder.emit(
                    phase="observation_added",
                    status="running",
                    title="吸收工具结果",
                    reason="工具参数验证失败，将错误写回上下文",
                    output=observation.to_dict(),
                )
                continue

            # --- V0.7: resolve permission details ---
            permission_details = self.tools.permission_details(action.tool_name, action.args)

            if spec is not None and spec.requires_permission:
                content = action.args.get("content")
                content_preview = preview_text(content) if isinstance(content, str) and content else ""

                self.recorder.emit(
                    phase="permission_requested",
                    status="waiting",
                    title=f"请求权限：{action.tool_name}",
                    reason=action.reason,
                    input={
                        "tool_name": action.tool_name,
                        "args": action.args,
                        "preview": content_preview,
                        "details": permission_details,
                    },
                    output={},
                )

                approved = self.permission_callback(action, permission_details)

                if approved:
                    self.recorder.emit(
                        phase="permission_resolved",
                        status="completed",
                        title="权限已批准",
                        reason=f"用户批准执行 {action.tool_name}",
                        input={"tool_name": action.tool_name, "args": action.args, "details": permission_details},
                        output={"approved": True},
                    )
                else:
                    self.recorder.emit(
                        phase="permission_resolved",
                        status="interrupted",
                        title="权限被拒绝",
                        reason=f"用户拒绝执行 {action.tool_name}",
                        input={"tool_name": action.tool_name, "args": action.args, "details": permission_details},
                        output={"approved": False},
                    )

                    rejected_observation = Observation(
                        tool_name=action.tool_name,
                        args=action.args,
                        result=ToolResult(
                            success=False,
                            error="permission denied by user",
                            metadata={"permission": "rejected"},
                        ),
                    )
                    self.observations.append(rejected_observation)
                    self.recorder.emit(
                        phase="observation_added",
                        status="running",
                        title="吸收工具结果",
                        reason="用户拒绝了权限，将拒绝结果写回上下文",
                        output=rejected_observation.to_dict(),
                    )
                    continue

            self._pause()
            self.recorder.emit(
                phase="tool_started",
                status="running",
                title=f"调用工具：{action.tool_name}",
                reason=action.reason,
                input={"tool_name": action.tool_name, "args": action.args},
            )

            result = self.tools.call(action.tool_name, action.args)
            event_status = "completed" if result.success else "failed"
            self.recorder.emit(
                phase="tool_finished",
                status=event_status,
                title=f"工具返回：{action.tool_name}",
                reason="工具执行完成" if result.success else "工具执行失败",
                output=result.to_dict(),
            )

            # V0.6: 只追踪成功读取的文件路径，正文以 Observation 为唯一来源
            if action.tool_name == "read_file" and result.success:
                path = action.args.get("path")
                if isinstance(path, str) and path not in self._selected_project_content:
                    self._selected_project_content.append(path)

            observation = Observation(tool_name=action.tool_name, args=action.args, result=result)
            self.observations.append(observation)
            self.recorder.emit(
                phase="observation_added",
                status="running",
                title="吸收工具结果",
                reason="把工具结果写回上下文，供下一轮判断使用",
                output=observation.to_dict(),
            )

        return self._fail("达到最大轮次限制，Agent 停止以避免无限循环")

    def _fail(self, message: str) -> AgentRunResult:
        self.recorder.emit(
            phase="run_failed",
            status="failed",
            title="任务失败",
            reason=message,
            output={"message": message},
        )
        return AgentRunResult(message=message, success=False)

    def _pause(self) -> None:
        if self.step_delay_seconds > 0:
            time.sleep(self.step_delay_seconds)
