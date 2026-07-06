from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from min_agent.types import (
    RunMemory,
    RunMemorySummary,
    RunMetadata,
    ToolCatalogEntry,
    ToolSpec,
    WorkspaceConfig,
)


def _normalize_workspace(raw: object) -> str:
    """规范化 workspace 路径用于跨 workspace 比较。"""
    if not isinstance(raw, str):
        return ""
    try:
        return str(Path(raw).resolve())
    except (OSError, RuntimeError):
        return raw


class ContextLoader:
    """从文件系统和 run records 中加载运行级基础上下文。

    不负责组装逐轮动态上下文（working_observations、selected_project_content）。
    """

    def __init__(self, workspace: str, runs_dir: str, decision_model: str) -> None:
        self._workspace_root = Path(workspace).resolve()
        self._runs_dir = Path(runs_dir)
        self._decision_model = decision_model

    # ------------------------------------------------------------------
    # workspace config
    # ------------------------------------------------------------------

    def load_workspace_config(self) -> WorkspaceConfig:
        """读取 <workspace>/minagent.md。

        文件不存在返回 status="not_found"。
        """
        candidate = self._workspace_root / "minagent.md"

        if not candidate.exists():
            return WorkspaceConfig(status="not_found", path="minagent.md")

        # symlink 越界检测
        try:
            real = candidate.resolve()
        except (OSError, RuntimeError):
            return WorkspaceConfig(
                status="error",
                path="minagent.md",
                error="symlink_resolve_failed",
            )

        try:
            if not real.is_relative_to(self._workspace_root):
                return WorkspaceConfig(
                    status="error",
                    path="minagent.md",
                    error="symlink_outside_workspace",
                )
        except ValueError:
            return WorkspaceConfig(
                status="error",
                path="minagent.md",
                error="symlink_outside_workspace",
            )

        # 读取文件（最多 8001 字符，避免无界内存占用）
        try:
            with open(candidate, encoding="utf-8") as fh:
                raw_text = fh.read(8001)
        except UnicodeDecodeError:
            return WorkspaceConfig(
                status="error",
                path="minagent.md",
                error="invalid_utf8",
            )
        except (PermissionError, OSError):
            return WorkspaceConfig(
                status="error",
                path="minagent.md",
                error="file_read_error",
            )

        content = raw_text[:8000]
        truncated = len(raw_text) > 8000
        preview = content[:200]

        return WorkspaceConfig(
            status="loaded",
            path="minagent.md",
            content=content,
            preview=preview,
            truncated=truncated,
        )

    # ------------------------------------------------------------------
    # run memory
    # ------------------------------------------------------------------

    def load_run_memory(self, max_count: int = 3) -> RunMemory:
        """读取 runs_dir 下最近 max_count 条 run record 摘要。

        跳过损坏、缺字段或无法解析的文件。
        没有可用文件返回 status="empty"。
        """
        runs_dir = self._runs_dir

        if not runs_dir.is_dir():
            return RunMemory(status="empty", summary_count=0)

        try:
            json_files = sorted(runs_dir.glob("*.json"))
        except OSError:
            return RunMemory(status="error", summary_count=0)

        current_workspace = _normalize_workspace(str(self._workspace_root))
        valid_records: list[dict[str, Any]] = []

        for json_path in json_files:
            record = self._parse_run_record(json_path)
            if record is None:
                continue
            # 跨 workspace 隔离
            record_workspace = _normalize_workspace(record.get("workspace", ""))
            if record_workspace != current_workspace:
                continue
            valid_records.append(record)

        # 按 started_at 降序排列后取前 max_count 条
        valid_records.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        top_records = valid_records[:max_count]

        summaries = [self._build_summary(record) for record in top_records]

        if not summaries:
            return RunMemory(status="empty", summary_count=0, summaries=[])

        return RunMemory(
            status="loaded",
            summary_count=len(summaries),
            summaries=summaries,
        )

    def _parse_run_record(self, path: Path) -> dict[str, Any] | None:
        """尝试解析单个 run record 文件，失败返回 None。"""
        try:
            raw = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            return None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        # 必须字段检查（含类型校验，防止 null / 畸形值导致下游崩溃）
        required_string_fields = ["run_id", "workspace", "started_at", "user_goal", "status"]
        for field in required_string_fields:
            if field not in data or not isinstance(data[field], str):
                return None

        if "events" not in data or not isinstance(data["events"], list):
            return None

        # 每个 event 元素必须是 dict，否则后续 .get() 会崩溃
        if not all(isinstance(e, dict) for e in data["events"]):
            return None

        return data

    def _build_summary(self, record: dict[str, Any]) -> RunMemorySummary:
        """从合法的 run record 中提取摘要。"""
        events: list[dict[str, Any]] = record.get("events", [])

        # 提取工具调用链
        key_tool_chain = self._extract_tool_chain(events)

        # 提取 final_answer 的前 200 字符
        final_answer_preview = ""
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("phase") == "final_answer":
                output = event.get("output")
                if isinstance(output, dict):
                    message = output.get("message", "")
                    if isinstance(message, str) and message:
                        final_answer_preview = message[:200]
                break

        # created_file_path：只来自成功的 write_file
        created_file_path = self._extract_created_file_path(events)

        return RunMemorySummary(
            run_id=record.get("run_id", ""),
            user_goal=record.get("user_goal", ""),
            status=record.get("status", ""),
            final_answer_preview=final_answer_preview,
            key_tool_chain=key_tool_chain,
            created_file_path=created_file_path,
        )

    @staticmethod
    def _extract_tool_chain(events: list[dict[str, Any]]) -> list[str]:
        """从 events 中收集所有 tool_started 的 tool_name。"""
        tool_names: list[str] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("phase") == "tool_started":
                input_data = event.get("input")
                if not isinstance(input_data, dict):
                    continue
                tool_name = input_data.get("tool_name")
                if isinstance(tool_name, str) and tool_name:
                    tool_names.append(tool_name)
        return tool_names

    @staticmethod
    def _extract_created_file_path(events: list[dict[str, Any]]) -> str:
        """从 events 中提取成功 write_file 创建的文件路径。

        在顺序 events 中，每个 tool_started 后紧随对应的 tool_finished。
        只有 write_file 的 tool_finished(success=true) 才记录 created_file_path。
        """
        last_tool_started: str | None = None
        write_args: dict[str, Any] | None = None
        for event in events:
            if not isinstance(event, dict):
                continue
            if event.get("phase") == "tool_started":
                input_data = event.get("input")
                if not isinstance(input_data, dict):
                    last_tool_started = None
                    write_args = None
                    continue
                last_tool_started = input_data.get("tool_name")
                if last_tool_started == "write_file":
                    raw_args = input_data.get("args")
                    write_args = raw_args if isinstance(raw_args, dict) else {}
                else:
                    write_args = None
            elif event.get("phase") == "tool_finished" and last_tool_started == "write_file" and write_args is not None:
                output = event.get("output")
                if not isinstance(output, dict):
                    write_args = None
                    continue
                if output.get("success") is True:
                    metadata = output.get("metadata")
                    if isinstance(metadata, dict):
                        path = metadata.get("path", "")
                        if isinstance(path, str) and path:
                            return path
                write_args = None
        return ""

    # ------------------------------------------------------------------
    # run metadata
    # ------------------------------------------------------------------

    def load_run_metadata(self, run_id: str, started_at: str, tool_count: int) -> RunMetadata:
        """组装本次运行的元信息。"""
        return RunMetadata(
            run_id=run_id,
            started_at=started_at,
            workspace=str(self._workspace_root),
            decision_model=self._decision_model,
            available_tool_count=tool_count,
        )

    # ------------------------------------------------------------------
    # tool catalog
    # ------------------------------------------------------------------

    def build_tool_catalog(self, tools: list[ToolSpec]) -> list[ToolCatalogEntry]:
        """将 ToolSpec 列表转为 ToolCatalogEntry 列表。"""
        return [
            ToolCatalogEntry(
                name=tool.name,
                description=tool.description,
                requires_permission=tool.requires_permission,
                args_schema=dict(tool.args_schema),
            )
            for tool in tools
        ]
