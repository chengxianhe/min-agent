from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ActionKind = Literal["create_plan", "complete_task", "tool_call", "final_answer"]
TaskStatus = Literal["pending", "running", "completed", "failed", "skipped"]
EventPhase = Literal[
    "run_started",
    "context_built",
    "llm_decision",
    "plan_created",
    "task_started",
    "task_completed",
    "task_failed",
    "task_skipped",
    "tool_started",
    "tool_finished",
    "observation_added",
    "permission_requested",
    "permission_resolved",
    "final_answer",
    "run_completed",
    "run_failed",
    "run_interrupted",
]
EventStatus = Literal["waiting", "running", "completed", "failed", "interrupted", "info"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_schema: dict[str, Any] = field(default_factory=dict)
    requires_permission: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ToolResult:
    success: bool
    content: str = ""
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskDefinition:
    task_id: str
    title: str
    completion_criteria: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    title: str
    completion_criteria: str
    status: TaskStatus
    failure_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Observation:
    tool_name: str
    args: dict[str, Any]
    result: ToolResult

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "args": self.args,
            "result": self.result.to_dict(),
        }


@dataclass(frozen=True)
class AgentAction:
    kind: ActionKind
    reason: str
    success: bool = True
    tool_name: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # V0.8: task plan and completion evidence
    tasks: list[TaskDefinition] = field(default_factory=list)
    task_id: str | None = None
    completion_evidence: str | None = None
    evidence_observation_indexes: list[int] = field(default_factory=list)

    @classmethod
    def tool_call(
        cls,
        tool_name: str,
        args: dict[str, Any],
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentAction:
        return cls(kind="tool_call", tool_name=tool_name, args=args, reason=reason, metadata=metadata or {})

    @classmethod
    def final_answer(
        cls,
        message: str,
        reason: str,
        success: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> AgentAction:
        return cls(kind="final_answer", message=message, reason=reason, success=success, metadata=metadata or {})

    @classmethod
    def create_plan(
        cls,
        tasks: list[TaskDefinition],
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentAction:
        return cls(kind="create_plan", tasks=list(tasks), reason=reason, metadata=metadata or {})

    @classmethod
    def complete_task(
        cls,
        task_id: str,
        completion_evidence: str,
        evidence_observation_indexes: list[int],
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> AgentAction:
        return cls(
            kind="complete_task",
            task_id=task_id,
            completion_evidence=completion_evidence,
            evidence_observation_indexes=list(evidence_observation_indexes),
            reason=reason,
            metadata=metadata or {},
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "reason": self.reason,
            "success": self.success,
            "tool_name": self.tool_name,
            "args": self.args,
            "message": self.message,
            "metadata": self.metadata,
            "tasks": [t.to_dict() for t in self.tasks],
            "task_id": self.task_id,
            "completion_evidence": self.completion_evidence,
            "evidence_observation_indexes": list(self.evidence_observation_indexes),
        }
        return result


# ===== V0.6 新增类型 =====


@dataclass(frozen=True)
class RunMetadata:
    """本次运行的基础信息。"""
    run_id: str
    started_at: str
    workspace: str
    decision_model: str
    available_tool_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkspaceConfig:
    """workspace 根目录 minagent.md 的加载结果。"""
    status: str            # "loaded" | "not_found" | "error"
    path: str              # 固定为 "minagent.md"
    content: str = ""      # 实际注入模型的内容，最多 8000 字符
    preview: str = ""      # 展示用前 200 字符
    truncated: bool = False
    error: str = ""        # 安全错误码，不记录 workspace 外真实路径

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunMemorySummary:
    """单条历史运行的摘要。"""
    run_id: str
    user_goal: str
    status: str
    final_answer_preview: str
    key_tool_chain: list[str]
    created_file_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunMemory:
    """最近运行摘要的集合。"""
    status: str                  # "loaded" | "empty" | "error"
    summary_count: int
    summaries: list[RunMemorySummary] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary_count": self.summary_count,
            "summaries": [s.to_dict() for s in self.summaries],
        }


@dataclass(frozen=True)
class ToolCatalogEntry:
    """工具目录单项。"""
    name: str
    description: str
    requires_permission: bool
    args_schema: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentContext:
    # === 既有字段（保持不变）===
    user_goal: str
    workspace: str
    available_tools: list[ToolSpec]
    observations: list[Observation]

    # === V0.6 新增字段 ===
    run_metadata: RunMetadata | None = None
    workspace_config: WorkspaceConfig | None = None
    run_memory: RunMemory | None = None
    tool_catalog: list[ToolCatalogEntry] = field(default_factory=list)
    selected_project_content: list[str] = field(default_factory=list)

    # === V0.8 新增字段 ===
    task_plan: list[TaskSnapshot] = field(default_factory=list)
    current_task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "user_goal": self.user_goal,
            "workspace": self.workspace,
            "available_tools": [tool.to_dict() for tool in self.available_tools],
            "observations": [observation.to_dict() for observation in self.observations],
        }
        if self.run_metadata is not None:
            result["run_metadata"] = self.run_metadata.to_dict()
        if self.workspace_config is not None:
            result["workspace_config"] = self.workspace_config.to_dict()
        if self.run_memory is not None:
            result["run_memory"] = self.run_memory.to_dict()
        if self.tool_catalog:
            result["tool_catalog"] = [entry.to_dict() for entry in self.tool_catalog]
        if self.selected_project_content:
            result["selected_project_content"] = list(self.selected_project_content)
        if self.task_plan:
            result["task_plan"] = [t.to_dict() for t in self.task_plan]
            result["current_task_id"] = self.current_task_id
        return result


@dataclass(frozen=True)
class AgentRunResult:
    message: str
    success: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TraceEvent:
    run_id: str
    step: int
    timestamp: str
    phase: EventPhase
    status: EventStatus
    title: str
    reason: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
