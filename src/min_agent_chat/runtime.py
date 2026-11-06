from __future__ import annotations

from pathlib import Path
from typing import Any

from min_agent.permission_broker import PermissionBroker
from min_agent.run_history import RUN_ID, RunHistory
from min_agent.run_manager import RunManager
from min_agent.session_key_store import SessionKeyStore


def trim(value: Any, limit: int = 12000) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n[内容已截断]"


class ChatRuntime:
    """One fixed demo workspace and one active run per MCP process."""

    def __init__(self, workspace: Path, runs_dir: Path, delay: float = 0.1):
        self.workspace = workspace.resolve(strict=True)
        self.history = RunHistory(runs_dir)
        self.permissions = PermissionBroker()
        self.manager = RunManager(
            self.workspace,
            runs_dir,
            SessionKeyStore(),
            self.permissions,
            step_delay_seconds=delay,
        )

    def start(self, goal: str) -> dict[str, Any]:
        return self.summarize(self.manager.start_run(goal, "fake"))

    def load(self, run_id: str) -> dict[str, Any]:
        if not RUN_ID.fullmatch(run_id):
            raise ValueError("无效任务编号")
        current = self.manager.current_snapshot()
        if current and current["run_id"] == run_id:
            return current
        return self.history.load_run(run_id)

    def summarize(self, run: dict[str, Any]) -> dict[str, Any]:
        events = run.get("events", [])
        permission = self.permissions.current()
        result = run.get("result") or {}
        final = result.get("message", "")
        if not final:
            final = next(
                (
                    e.get("output", {}).get("message", "")
                    for e in reversed(events)
                    if e["phase"] in ("final_answer", "run_failed")
                ),
                "",
            )
        tasks = next(
            (
                e.get("output", {}).get("tasks", [])
                for e in reversed(events)
                if isinstance(e.get("output", {}).get("tasks"), list)
            ),
            [],
        )
        artifacts = []
        files = []
        for event in events:
            output = event.get("output", {})
            if event["phase"] == "task_artifact_created":
                artifact = output.get("artifact", {})
                artifacts.append(
                    {
                        "task_id": artifact.get("task_id"),
                        "title": artifact.get("title"),
                        "content": trim(artifact.get("content"), 4000),
                    }
                )
            if (
                event["phase"] == "observation_added"
                and output.get("tool_name") == "write_file"
                and output.get("result", {}).get("success") is True
            ):
                args = output.get("args", {})
                files.append(
                    {
                        "path": args.get("path"),
                        "content": trim(args.get("content")),
                        "source": "本次成功写入时的内容快照",
                    }
                )
        last = events[-1] if events else {}
        return {
            "run_id": run["run_id"],
            "goal": run["user_goal"],
            "status": run["status"],
            "decision_model": run.get("decision_model", "fake"),
            "demo_mode": True,
            "event_count": len(events),
            "latest_step": last.get("title", "等待开始"),
            "latest_reason": trim(last.get("reason"), 500),
            "final_answer": trim(final),
            "tasks": tasks,
            "artifacts": artifacts,
            "files": files,
            "permission": permission.to_public_dict()
            if permission
            and permission.run_id == run["run_id"]
            and permission.status == "pending"
            else None,
        }

    def get(self, run_id: str) -> dict[str, Any]:
        return self.summarize(self.load(run_id))

    def trace(
        self, run_id: str, after_step: int = 0, limit: int = 10
    ) -> dict[str, Any]:
        if after_step < 0 or not 1 <= limit <= 30:
            raise ValueError("after_step 必须非负，limit 必须为 1–30")
        events = [e for e in self.load(run_id)["events"] if e["step"] > after_step]
        rows = [
            {
                "step": e["step"],
                "phase": e["phase"],
                "status": e["status"],
                "title": e["title"],
                "reason": trim(e.get("reason"), 500),
                "output": trim(e.get("output"), 1500),
            }
            for e in events[:limit]
        ]
        return {
            "run_id": run_id,
            "events": rows,
            "has_more": len(events) > limit,
            "next_after_step": rows[-1]["step"] if rows else after_step,
        }

    def list_runs(self, limit: int = 10) -> dict[str, Any]:
        if not 1 <= limit <= 30:
            raise ValueError("limit 必须为 1–30")
        history = self.history.list_runs()
        rows = [
            {k: v for k, v in row.items() if k != "final_answer"}
            for row in history.runs[:limit]
        ]
        current = self.manager.current_snapshot()
        return {
            "current": self.summarize(current) if current else None,
            "history": rows,
            "total": len(history.runs),
            "load_error_count": history.load_error_count,
        }

    def pending(self, run_id: str, permission_id: str) -> dict[str, Any]:
        request = self.permissions.current()
        if (
            not request
            or request.status != "pending"
            or request.run_id != run_id
            or request.permission_id != permission_id
        ):
            raise ValueError("权限申请已失效或不属于此任务，请重新查询任务")
        return request.to_public_dict()

    def close(self) -> None:
        self.manager.close()
