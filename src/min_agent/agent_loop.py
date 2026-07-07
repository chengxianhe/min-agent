from __future__ import annotations

import time
from collections.abc import Callable

from min_agent.context_builder import ContextBuilder
from min_agent.decision_model import DecisionModel
from min_agent.task_plan import TaskPlan, TaskPlanError
from min_agent.tool_registry import ToolRegistry
from min_agent.trace_recorder import TraceRecorder
from min_agent.types import AgentAction, AgentRunResult, Observation, TaskDefinition, ToolResult


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
        composite_max_turns: int = 20,
        step_delay_seconds: float = 0.4,
        permission_callback: Callable[[AgentAction, dict[str, Any]], bool] | None = None,
    ) -> None:
        self.context_builder = context_builder
        self.llm = llm
        self.tools = tools
        self.recorder = recorder
        self.workspace = workspace
        self.max_turns = max_turns
        self.composite_max_turns = composite_max_turns
        self.step_delay_seconds = step_delay_seconds
        self.permission_callback = permission_callback or (lambda _action, _details: False)
        self.observations: list[Observation] = []
        self._selected_project_content: list[str] = []

        # V0.8: 任务计划状态
        self.task_plan: TaskPlan | None = None
        self._task_observations: list[Observation] = []
        self._has_started_tool: bool = False

    # ---- helpers ----

    def _current_task_id(self) -> str | None:
        if self.task_plan is None:
            return None
        current = self.task_plan.current_task()
        return current.task_id if current else None

    def _emit(self, phase: str, status: str, title: str, reason: str = "",
              input: dict | None = None, output: dict | None = None) -> None:
        """Emit a trace event automatically scoped to the current task."""
        self.recorder.emit(
            phase=phase,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            title=title,
            reason=reason,
            input=input or {},
            output=output or {},
            task_id=self._current_task_id(),
        )

    def _emit_task_event(self, phase: str, task_id: str, reason: str = "",
                         failure_reason: str = "") -> None:
        """Emit a task-scoped event with explicit task snapshot output."""
        output: dict = {}
        if self.task_plan:
            snap = self.task_plan.snapshot()
            output["tasks"] = [t.to_dict() for t in snap]
        if task_id:
            output["task_id"] = task_id
        if failure_reason:
            output["failure_reason"] = failure_reason

        self.recorder.emit(
            phase=phase,  # type: ignore[arg-type]
            status="running" if phase in ("task_started",) else
                   "completed" if phase in ("task_completed",) else
                   "failed" if phase == "task_failed" else
                   "info",
            title={
                "plan_created": "计划已生成",
                "task_started": "开始任务",
                "task_completed": "任务完成",
                "task_failed": "任务失败",
                "task_skipped": "任务跳过",
            }.get(phase, phase),
            reason=reason,
            output=output,
            task_id=task_id if phase != "plan_created" else None,
        )

    def _clear_task_buffer(self) -> None:
        self._task_observations = []

    def _run_failed_event(self, message: str) -> None:
        """Emit run-level failed events (task_id=None in composite mode)."""
        tid = None if self.task_plan else self._current_task_id()
        self.recorder.emit(
            phase="final_answer",
            status="failed",
            title="生成最终回答",
            reason=message,
            output={"message": message},
            task_id=None if self.task_plan is not None else tid,
        )
        self.recorder.emit(
            phase="run_failed",
            status="failed",
            title="任务失败",
            reason=message,
            output={"message": message},
            task_id=None if self.task_plan is not None else tid,
        )

    def _build_failure_message(self) -> str:
        """Build deterministic failure message enumerating task statuses."""
        if self.task_plan is None:
            return "任务执行失败"

        snap = self.task_plan.snapshot()
        completed = [t for t in snap if t.status == "completed"]
        failed = [t for t in snap if t.status == "failed"]
        skipped = [t for t in snap if t.status == "skipped"]

        parts = []
        if completed:
            names = "、".join(t.title for t in completed)
            parts.append(f"已完成：{names}")
        if failed:
            for t in failed:
                parts.append(f"失败：{t.title}（{t.failure_reason}）")
        if skipped:
            names = "、".join(t.title for t in skipped)
            parts.append(f"跳过：{names}")
        return "\n".join(parts) if parts else "任务执行失败"

    # ---- main loop ----

    def run(self, user_goal: str) -> AgentRunResult:
        self.recorder.emit(
            phase="run_started",
            status="running",
            title="收到任务",
            reason="用户提交了一个目标",
            input={"user_goal": user_goal, "workspace": self.workspace},
        )

        effective_max = self.max_turns

        for _turn in range(max(self.max_turns, self.composite_max_turns)):
            # 动态预算切换
            if _turn >= effective_max:
                if self.task_plan is not None and self.task_plan.current_task() is not None:
                    # 复合模式预算耗尽
                    self._fail_current_task("达到最大轮次限制")
                    msg = self._build_failure_message()
                    self._run_failed_event(msg)
                    return AgentRunResult(message=msg, success=False)
                else:
                    msg = "达到最大轮次限制，Agent 停止以避免无限循环"
                    return self._fail(msg)

            self._pause()
            context = self.context_builder.build(
                user_goal=user_goal,
                workspace=self.workspace,
                available_tools=self.tools.list_specs(),
                observations=self._task_observations if self.task_plan else self.observations,
                selected_project_content=self._selected_project_content,
                run_id=self.recorder.run_id,
                started_at=self.recorder.started_at,
                task_plan=self.task_plan.snapshot() if self.task_plan else None,
                current_task_id=self._current_task_id(),
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

            # ---- V0.8: handle create_plan ----
            if action.kind == "create_plan":
                result = self._handle_create_plan(action, user_goal)
                if result is not None:
                    return result
                # 仅在 max_turns 为默认值 8 时切换到复合预算
                if self.max_turns == 8:
                    effective_max = self.composite_max_turns
                continue

            # ---- V0.8: handle complete_task ----
            if action.kind == "complete_task":
                result = self._handle_complete_task(action)
                if result is not None:
                    return result
                continue

            # ---- final_answer ----
            if action.kind == "final_answer":
                return self._handle_final_answer(action)

            # ---- tool_call (V0.7 path) ----
            result = self._handle_tool_call(action)
            if result is not None:
                return result

        msg = "达到最大轮次限制，Agent 停止以避免无限循环"
        return self._fail(msg)

    # ---- action handlers ----

    def _handle_create_plan(self, action: AgentAction, user_goal: str) -> AgentRunResult | None:
        """Handle create_plan action. Returns result on failure, None to continue."""
        # 非法检查：计划已存在或工具已调用过
        if self.task_plan is not None or self._has_started_tool:
            msg = "模型在非法时机尝试创建计划"
            self.recorder.emit(
                phase="llm_decision",
                status="failed",
                title="决定下一步",
                reason=msg,
                output=action.to_dict(),
            )
            self._run_failed_event(msg)
            return AgentRunResult(message=msg, success=False)

        # 验证并创建计划
        try:
            plan = TaskPlan.create(action.tasks)
        except TaskPlanError as e:
            msg = f"计划创建失败：{e}"
            self.recorder.emit(
                phase="llm_decision",
                status="failed",
                title="决定下一步",
                reason=msg,
                output=action.to_dict(),
            )
            self._run_failed_event(msg)
            return AgentRunResult(message=msg, success=False)

        self.task_plan = plan
        snapshot = plan.snapshot()
        self._emit_task_event(
            "plan_created", "",
            reason=f"为目标生成 {len(snapshot)} 个任务的固定计划",
        )

        # 启动第一个任务
        first = plan.start_next()
        if first is not None:
            self._clear_task_buffer()
            self._emit_task_event("task_started", first.task_id,
                                  reason=f"开始执行：{first.title}")

        return None  # continue loop

    def _handle_complete_task(self, action: AgentAction) -> AgentRunResult | None:
        """Handle complete_task action. Returns result on failure, None to continue."""
        if self.task_plan is None:
            # 简单模式下不识别 complete_task
            msg = "当前运行没有任务计划，无法完成任务"
            self.recorder.emit(
                phase="llm_decision",
                status="failed",
                title="决定下一步",
                reason=msg,
                output=action.to_dict(),
            )
            self._run_failed_event(msg)
            return AgentRunResult(message=msg, success=False)

        try:
            completed = self.task_plan.complete_current(
                action.task_id or "",
                action.completion_evidence or "",
                list(action.evidence_observation_indexes),
                list(self._task_observations),
            )
        except TaskPlanError as e:
            # 完成证据无效 → 失败当前任务
            self._fail_current_task(str(e))
            msg = self._build_failure_message()
            self._run_failed_event(msg)
            return AgentRunResult(message=msg, success=False)

        self._emit_task_event("task_completed", completed.task_id,
                              reason=f"完成：{completed.title}")

        # 检查是否全部完成
        if self.task_plan.all_completed():
            return None  # 让模型通过 final_answer 结束

        # 启动下一个任务
        next_task = self.task_plan.start_next()
        if next_task is not None:
            self._clear_task_buffer()
            self._emit_task_event("task_started", next_task.task_id,
                                  reason=f"开始执行：{next_task.title}")

        return None  # continue loop

    def _handle_final_answer(self, action: AgentAction) -> AgentRunResult:
        """Handle final_answer action."""
        message = action.message or ""
        status = "completed" if action.success else "failed"

        # 复合模式：检查是否所有任务完成
        if self.task_plan is not None:
            if action.success and not self.task_plan.all_completed():
                # 过早宣告成功 → 失败
                current = self.task_plan.current_task()
                reason = "模型在任务未全部完成时提前宣告成功"
                if current:
                    self._fail_current_task(reason)
                msg = self._build_failure_message()
                self._run_failed_event(msg)
                return AgentRunResult(message=msg, success=False)

            if not action.success:
                current = self.task_plan.current_task()
                if current:
                    self._fail_current_task("模型返回失败结果")
                msg = self._build_failure_message()
                self._run_failed_event(msg)
                return AgentRunResult(message=msg, success=False)

        # 成功或简单模式
        self.recorder.emit(
            phase="final_answer",
            status=status,
            title="生成最终回答",
            reason=action.reason,
            output={"message": message},
            task_id=None if self.task_plan is not None else None,
        )
        run_phase = "run_completed" if status == "completed" else "run_failed"
        self.recorder.emit(
            phase=run_phase,  # type: ignore[arg-type]
            status=status,
            title="任务完成" if status == "completed" else "任务失败",
            output={"message": message},
            task_id=None if self.task_plan is not None else None,
        )
        return AgentRunResult(message=message, success=action.success)

    def _handle_tool_call(self, action: AgentAction) -> AgentRunResult | None:
        """Handle tool_call action. Returns result on failure in composite mode, None to continue."""
        self._has_started_tool = True

        if action.tool_name is None:
            msg = "模型返回了工具调用，但没有提供工具名称"
            return self._maybe_fail_or_continue(msg)

        # --- preflight validation ---
        spec = self.tools.get_spec(action.tool_name)
        validation_error = self.tools.validate_call(action.tool_name, action.args)
        if validation_error is not None:
            observation = Observation(
                tool_name=action.tool_name,
                args=action.args,
                result=validation_error,
            )
            self._append_observation(observation)
            self._emit("observation_added", "running", "吸收工具结果",
                       reason="工具参数验证失败，将错误写回上下文",
                       output=observation.to_dict())
            return self._maybe_fail_or_continue(
                f"工具参数验证失败：{validation_error.error}",
                skip_tool_started=True,
            )

        # --- permission ---
        permission_details = self.tools.permission_details(action.tool_name, action.args)

        if spec is not None and spec.requires_permission:
            content = action.args.get("content")
            content_preview = preview_text(content) if isinstance(content, str) and content else ""

            self._emit("permission_requested", "waiting",
                       f"请求权限：{action.tool_name}",
                       reason=action.reason,
                       input={
                           "tool_name": action.tool_name,
                           "args": action.args,
                           "preview": content_preview,
                           "details": permission_details,
                       })

            approved = self.permission_callback(action, permission_details)

            if approved:
                self._emit("permission_resolved", "completed", "权限已批准",
                           reason=f"用户批准执行 {action.tool_name}",
                           input={"tool_name": action.tool_name, "args": action.args, "details": permission_details},
                           output={"approved": True})
            else:
                self._emit("permission_resolved", "interrupted", "权限被拒绝",
                           reason=f"用户拒绝执行 {action.tool_name}",
                           input={"tool_name": action.tool_name, "args": action.args, "details": permission_details},
                           output={"approved": False})

                rejected_observation = Observation(
                    tool_name=action.tool_name,
                    args=action.args,
                    result=ToolResult(
                        success=False,
                        error="permission denied by user",
                        metadata={"permission": "rejected"},
                    ),
                )
                self._append_observation(rejected_observation)
                self._emit("observation_added", "running", "吸收工具结果",
                           reason="用户拒绝了权限，将拒绝结果写回上下文",
                           output=rejected_observation.to_dict())
                return self._maybe_fail_or_continue(
                    f"用户拒绝执行 {action.tool_name}",
                    skip_tool_started=True,
                )

        # --- execute ---
        self._pause()
        self._emit("tool_started", "running", f"调用工具：{action.tool_name}",
                   reason=action.reason,
                   input={"tool_name": action.tool_name, "args": action.args})

        result = self.tools.call(action.tool_name, action.args)
        event_status = "completed" if result.success else "failed"
        self._emit("tool_finished", event_status, f"工具返回：{action.tool_name}",
                   reason="工具执行完成" if result.success else "工具执行失败",
                   output=result.to_dict())

        # Track read files
        if action.tool_name == "read_file" and result.success:
            path = action.args.get("path")
            if isinstance(path, str) and path not in self._selected_project_content:
                self._selected_project_content.append(path)

        observation = Observation(tool_name=action.tool_name, args=action.args, result=result)
        self._append_observation(observation)
        self._emit("observation_added", "running", "吸收工具结果",
                   reason="把工具结果写回上下文，供下一轮判断使用",
                   output=observation.to_dict())

        # 复合模式：工具失败 → 失败当前任务
        if self.task_plan is not None and not result.success:
            self._fail_current_task(f"工具 {action.tool_name} 执行失败：{result.error or 'unknown error'}")
            msg = self._build_failure_message()
            self._run_failed_event(msg)
            return AgentRunResult(message=msg, success=False)

        return None  # continue loop

    # ---- observation management ----

    def _append_observation(self, observation: Observation) -> None:
        """Append observation to both global list and current-task buffer."""
        self.observations.append(observation)
        if self.task_plan is not None and self.task_plan.current_task() is not None:
            self._task_observations.append(observation)

    # ---- failure handling ----

    def _fail_current_task(self, reason: str) -> None:
        """Fail the current task and skip remaining pending tasks."""
        if self.task_plan is None:
            return
        try:
            failed, skipped = self.task_plan.fail_current(reason)
            self._emit_task_event("task_failed", failed.task_id,
                                  failure_reason=reason)
            for s in skipped:
                self._emit_task_event("task_skipped", s.task_id,
                                      failure_reason=s.failure_reason)
        except TaskPlanError:
            pass
        self._clear_task_buffer()

    def _maybe_fail_or_continue(self, message: str,
                                skip_tool_started: bool = False) -> AgentRunResult | None:
        """In composite mode: fail current task and stop. In simple mode: return observation and continue."""
        if self.task_plan is not None:
            self._fail_current_task(message)
            msg = self._build_failure_message()
            self._run_failed_event(msg)
            return AgentRunResult(message=msg, success=False)
        return None  # V0.7: continue loop

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
