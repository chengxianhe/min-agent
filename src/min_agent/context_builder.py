from __future__ import annotations

from typing import TYPE_CHECKING

from min_agent.types import (
    AgentContext,
    Observation,
    RunMemory,
    RunMetadata,
    TaskSnapshot,
    TaskArtifact,
    ToolCatalogEntry,
    ToolSpec,
    WorkspaceConfig,
)

if TYPE_CHECKING:
    from min_agent.context_loader import ContextLoader


class ContextBuilder:
    def __init__(self, context_loader: ContextLoader | None = None):
        self._loader = context_loader
        self._run_metadata: RunMetadata | None = None
        self._workspace_config: WorkspaceConfig | None = None
        self._run_memory: RunMemory | None = None
        self._tool_catalog: list[ToolCatalogEntry] = []
        self._base_context_loaded = False

    def build(
        self,
        user_goal: str,
        workspace: str,
        available_tools: list[ToolSpec],
        observations: list[Observation],
        selected_project_content: list[str] | None = None,
        run_id: str = "",
        started_at: str = "",
        task_plan: list[TaskSnapshot] | None = None,
        current_task_id: str | None = None,
        inherited_task_artifacts: list[TaskArtifact] | None = None,
    ) -> AgentContext:
        # 首次调用时加载运行级基础上下文（运行期间不变）
        if self._loader is not None and not self._base_context_loaded:
            self._workspace_config = self._loader.load_workspace_config()
            self._run_memory = self._loader.load_run_memory()
            self._tool_catalog = self._loader.build_tool_catalog(available_tools)
            self._run_metadata = self._loader.load_run_metadata(
                run_id=run_id,
                started_at=started_at,
                tool_count=len(available_tools),
            )
            self._base_context_loaded = True

        return AgentContext(
            user_goal=user_goal,
            workspace=workspace,
            available_tools=list(available_tools),
            observations=list(observations),
            run_metadata=self._run_metadata,
            workspace_config=self._workspace_config,
            run_memory=self._run_memory,
            tool_catalog=list(self._tool_catalog),
            selected_project_content=list(selected_project_content or []),
            task_plan=list(task_plan) if task_plan else [],
            current_task_id=current_task_id,
            inherited_task_artifacts=list(inherited_task_artifacts or []),
        )
