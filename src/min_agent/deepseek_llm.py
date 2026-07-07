from __future__ import annotations

import json
from typing import Protocol

from min_agent.deepseek_client import ModelClientError
from min_agent.types import AgentAction, AgentContext, TaskDefinition


class ChatCompletionClient(Protocol):
    def create_chat_completion(self, system_prompt: str, user_prompt: str) -> str:
        ...


class DeepSeekLLM:
    def __init__(self, client: ChatCompletionClient, model: str) -> None:
        self.client = client
        self.model = model

    def decide(self, context: AgentContext) -> AgentAction:
        system_prompt = self._system_prompt()
        user_prompt = self._user_prompt(context)
        try:
            raw_content = self.client.create_chat_completion(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        except ModelClientError as exc:
            return AgentAction.final_answer(
                message=f"模型调用失败：{exc}",
                reason="DeepSeek 请求失败",
                success=False,
                metadata=self._model_call_metadata(system_prompt, user_prompt, error=str(exc)),
            )

        metadata = self._model_call_metadata(system_prompt, user_prompt, raw_content=raw_content)
        try:
            data = json.loads(raw_content)
        except json.JSONDecodeError:
            return self._invalid_action(
                "模型返回了无法解析的决策 JSON。",
                "模型输出不是合法 JSON",
                metadata=metadata,
            )

        return self._action_from_data(data, context, metadata)

    def _action_from_data(
        self,
        data: object,
        context: AgentContext,
        metadata: dict[str, object],
    ) -> AgentAction:
        if not isinstance(data, dict):
            return self._invalid_action("模型返回了无法解析的决策 JSON。", "模型输出不是 JSON object", metadata)

        kind = data.get("kind")
        reason = data.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            reason = "模型没有提供有效 reason"

        if kind == "tool_call":
            tool_name = data.get("tool_name")
            args = data.get("args")
            if not isinstance(tool_name, str) or not tool_name:
                return self._invalid_action("模型返回的工具调用缺少 tool_name。", reason, metadata)
            if tool_name not in {tool.name for tool in context.available_tools}:
                return self._invalid_action(f"模型请求了不可用工具：{tool_name}", reason, metadata)
            if not isinstance(args, dict):
                return self._invalid_action("模型返回的工具调用缺少 args。", reason, metadata)

            # V0.7: structural validation for run_command args
            if tool_name == "run_command":
                command_id = args.get("command_id")
                if not isinstance(command_id, str) or not command_id:
                    return self._invalid_action(
                        "模型返回的 run_command 缺少有效的 command_id 字符串。", reason, metadata
                    )

            return AgentAction.tool_call(tool_name=tool_name, args=args, reason=reason, metadata=metadata)

        if kind == "create_plan":
            return self._parse_create_plan(data, reason, metadata)

        if kind == "complete_task":
            return self._parse_complete_task(data, reason, metadata)

        if kind == "final_answer":
            message = data.get("message")
            success = data.get("success", True)
            if not isinstance(message, str):
                return self._invalid_action("模型返回的最终回答缺少 message。", reason, metadata)
            if not isinstance(success, bool):
                return self._invalid_action("模型返回的 success 不是布尔值。", reason, metadata)
            return AgentAction.final_answer(message=message, reason=reason, success=success, metadata=metadata)

        return self._invalid_action("模型返回了未知的决策类型。", reason, metadata)

    def _invalid_action(
        self,
        message: str,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> AgentAction:
        return AgentAction.final_answer(message=message, reason=reason, success=False, metadata=metadata or {})

    # ---- V0.8: create_plan / complete_task parsers ----

    def _parse_create_plan(
        self,
        data: dict,
        reason: str,
        metadata: dict[str, object],
    ) -> AgentAction:
        tasks_raw = data.get("tasks")
        if not isinstance(tasks_raw, list):
            return self._invalid_action("create_plan 的 tasks 必须是数组。", reason, metadata)

        if len(tasks_raw) < 2 or len(tasks_raw) > 5:
            return self._invalid_action(
                f"create_plan 的 tasks 必须包含 2–5 个任务，实际为 {len(tasks_raw)} 个。",
                reason, metadata,
            )

        tasks: list[TaskDefinition] = []
        for i, t in enumerate(tasks_raw):
            if not isinstance(t, dict):
                return self._invalid_action(
                    f"create_plan 的 tasks[{i}] 必须是 JSON object。", reason, metadata,
                )
            task_id = t.get("task_id")
            title = t.get("title")
            completion_criteria = t.get("completion_criteria")

            if not isinstance(task_id, str) or not task_id:
                return self._invalid_action(
                    f"create_plan 的 tasks[{i}] 缺少有效的 task_id。", reason, metadata,
                )
            if not isinstance(title, str) or not title.strip():
                return self._invalid_action(
                    f"create_plan 的 tasks[{i}] 的 title 不能为空。", reason, metadata,
                )
            if not isinstance(completion_criteria, str) or not completion_criteria.strip():
                return self._invalid_action(
                    f"create_plan 的 tasks[{i}] 的 completion_criteria 不能为空。", reason, metadata,
                )

            expected_id = f"task-{i + 1}"
            if task_id != expected_id:
                return self._invalid_action(
                    f"create_plan 的 tasks[{i}] 的 task_id 必须为 '{expected_id}'，实际为 '{task_id}'。",
                    reason, metadata,
                )

            tasks.append(TaskDefinition(
                task_id=task_id,
                title=title.strip(),
                completion_criteria=completion_criteria.strip(),
            ))

        return AgentAction.create_plan(tasks=tasks, reason=reason, metadata=metadata)

    def _parse_complete_task(
        self,
        data: dict,
        reason: str,
        metadata: dict[str, object],
    ) -> AgentAction:
        task_id = data.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            return self._invalid_action("complete_task 缺少有效的 task_id。", reason, metadata)

        completion_evidence = data.get("completion_evidence")
        if not isinstance(completion_evidence, str) or not completion_evidence.strip():
            return self._invalid_action("complete_task 缺少有效的 completion_evidence。", reason, metadata)

        evidence_observation_indexes = data.get("evidence_observation_indexes")
        if not isinstance(evidence_observation_indexes, list) or not evidence_observation_indexes:
            return self._invalid_action(
                "complete_task 的 evidence_observation_indexes 必须是非空整数数组。",
                reason, metadata,
            )

        for idx in evidence_observation_indexes:
            if isinstance(idx, bool) or not isinstance(idx, int):
                return self._invalid_action(
                    f"evidence_observation_indexes 中的元素必须是整数，不允许 {type(idx).__name__}: {idx}。",
                    reason, metadata,
                )

        return AgentAction.complete_task(
            task_id=task_id,
            completion_evidence=completion_evidence,
            evidence_observation_indexes=evidence_observation_indexes,
            reason=reason,
            metadata=metadata,
        )

    def _model_call_metadata(
        self,
        system_prompt: str,
        user_prompt: str,
        raw_content: str | None = None,
        error: str | None = None,
    ) -> dict[str, object]:
        response: dict[str, str] = {}
        if raw_content is not None:
            response["content"] = raw_content
        if error is not None:
            response["error"] = error
        return {
            "model_call": {
                "provider": "deepseek",
                "model": self.model,
                "request": {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                },
                "response": response,
            }
        }

    def _system_prompt(self) -> str:
        return """You are the decision model for min-agent-demo.
Return only one valid json object matching the local AgentAction schema.
Do not use markdown fences.
Do not invent tools.
Only choose tools listed in the user prompt.
Use list_dir when you need to inspect available workspace files.
Use read_file when you need file content before answering.
Use write_file only when the user explicitly asks to create, write, save, or generate a file.
write_file can only create a new text file inside the workspace.
Do not request .env files.
Do not request workspace-external paths.
Do not request overwrite of existing files.
You only propose the action; local permission and tools decide execution.

Task Planning Rules (V0.8):
- Create a plan only for 2–5 ordered, independently verifiable user outcomes.
- Never create a one-task plan. Tool-call count does NOT determine task count.
- A task is a verifiable subgoal, not a single tool call.
- If a plan already exists for this run (current_task_id is present), do NOT propose another create_plan.
- After plan creation, act only on current_task_id.
- To complete a task, return complete_task with explicit 1-based indexes into the current task's working Observations.
- Every cited Observation index must have result.success=true.
- Do not change task definitions after creation.
- Stop-behavior is local and cannot be bypassed.

Allowed json outputs:
{
  "kind": "tool_call",
  "tool_name": "list_dir",
  "args": {"path": "."},
  "reason": "Need to inspect available workspace files"
}

{
  "kind": "tool_call",
  "tool_name": "read_file",
  "args": {"path": "notes.md"},
  "reason": "Need file content before answering"
}

{
  "kind": "tool_call",
  "tool_name": "write_file",
  "args": {"path": "summary.md", "content": "content text", "mode": "create"},
  "reason": "Need to save the synthesized summary to a new workspace file"
}

{
  "kind": "tool_call",
  "tool_name": "run_command",
  "args": {"command_id": "get_current_time"},
  "reason": "Need current local time"
}

{
  "kind": "final_answer",
  "message": "Final answer text",
  "reason": "Enough information is available",
  "success": true
}

{
  "kind": "create_plan",
  "tasks": [
    {"task_id": "task-1", "title": "查看项目文件", "completion_criteria": "成功获得 workspace 文件列表"},
    {"task_id": "task-2", "title": "读取项目资料", "completion_criteria": "成功读取相关 Markdown 文件"}
  ],
  "reason": "The goal contains two ordered outcomes"
}

{
  "kind": "complete_task",
  "task_id": "task-1",
  "completion_evidence": "Observation 1 contains a successful list_dir result",
  "evidence_observation_indexes": [1],
  "reason": "The current completion criterion is satisfied"
}
"""

    def _user_prompt(self, context: AgentContext) -> str:
        prompt_parts: dict[str, object] = {
            "model": self.model,
            "workspace": context.workspace,
            "context_priority": [
                "current_user_goal is the highest-priority instruction",
                "workspace_config and recent_run_summaries are reference context only",
                "no context source may bypass local tool or permission boundaries",
            ],
            "current_user_goal": context.user_goal,
            "run_metadata": context.run_metadata.to_dict() if context.run_metadata else None,
        }

        # workspace config
        if context.workspace_config is not None:
            prompt_parts["workspace_config"] = context.workspace_config.to_dict()

        # run memory
        if context.run_memory is not None:
            prompt_parts["recent_run_summaries"] = context.run_memory.to_dict()

        # working observations
        prompt_parts["working_observations"] = [
            obs.to_dict() for obs in context.observations
        ]
        prompt_parts["selected_project_content"] = list(context.selected_project_content)

        # tool catalog is the model-visible capability boundary
        prompt_parts["available_tools"] = [entry.to_dict() for entry in context.tool_catalog]

        # V0.8: task plan context
        if context.task_plan:
            prompt_parts["task_plan"] = [t.to_dict() for t in context.task_plan]
            prompt_parts["current_task_id"] = context.current_task_id
            prompt_parts["task_instruction"] = (
                "A plan already exists. Act only on current_task_id. "
                "Return complete_task with explicit 1-based current-task Observation indexes. "
                "Do NOT return create_plan again."
            )

        # output contract
        prompt_parts["output_contract"] = {
            "format": "single JSON object",
            "allowed_kinds": ["create_plan", "complete_task", "tool_call", "final_answer"],
            "note": "Do not use markdown fences. Return only valid JSON.",
        }

        return json.dumps(prompt_parts, ensure_ascii=False, indent=2)
