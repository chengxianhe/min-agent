from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_RUN_RECORD_BYTES = 10 * 1024 * 1024


class HistoryNotFound(FileNotFoundError):
    pass


@dataclass(frozen=True)
class HistoryListResult:
    runs: list[dict[str, Any]]
    load_error_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs": self.runs,
            "load_error_count": self.load_error_count,
        }


class RunHistory:
    """Loads terminal run records without enabling replay side effects."""

    def __init__(self, runs_dir: Path | str) -> None:
        self.runs_dir = Path(runs_dir).resolve()

    def _path(self, run_id: str) -> Path:
        if not RUN_ID.fullmatch(run_id):
            raise HistoryNotFound("Invalid run ID")

        path = (self.runs_dir / f"{run_id}.json").resolve()
        if self.runs_dir not in path.parents:
            raise HistoryNotFound("Run not found")
        return path

    def _load(self, path: Path, expected: str | None = None) -> dict[str, Any]:
        try:
            if path.stat().st_size > MAX_RUN_RECORD_BYTES:
                raise ValueError("Run record too large")
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise HistoryNotFound("Run not found") from exc

        if not isinstance(data, dict) or not RUN_ID.fullmatch(str(data.get("run_id", ""))):
            raise HistoryNotFound("Run not found")
        if expected and data["run_id"] != expected:
            raise HistoryNotFound("Run not found")
        if (
            data.get("status") not in {"completed", "failed", "interrupted"}
            or not isinstance(data.get("user_goal"), str)
            or not isinstance(data.get("started_at"), str)
            or not isinstance(data.get("events"), list)
        ):
            raise HistoryNotFound("Run not found")

        for event in data["events"]:
            if (
                not isinstance(event, dict)
                or event.get("run_id") != data["run_id"]
                or not isinstance(event.get("step"), int)
            ):
                raise HistoryNotFound("Run not found")

        data.setdefault("decision_model", "unknown")
        return data

    def load_run(self, run_id: str) -> dict[str, Any]:
        return self._load(self._path(run_id), run_id)

    def _summary(self, data: dict[str, Any]) -> dict[str, Any]:
        events = data["events"]
        plan = next(
            (
                event.get("output", {}).get("tasks", [])
                for event in events
                if event.get("phase") == "plan_created"
            ),
            [],
        )
        completed = sum(
            1 for event in events if event.get("phase") == "task_completed"
        )
        answer = next(
            (
                str(event.get("output", {}).get("message", ""))
                for event in reversed(events)
                if event.get("phase") == "final_answer"
            ),
            "",
        )
        return {
            "run_id": data["run_id"],
            "goal": data["user_goal"],
            "decision_model": data["decision_model"],
            "status": data["status"],
            "created_at": data["started_at"],
            "finished_at": data.get("ended_at"),
            "completed_tasks": completed,
            "total_tasks": len(plan),
            "final_answer": answer,
        }

    def list_runs(self) -> HistoryListResult:
        if not self.runs_dir.exists():
            return HistoryListResult([], 0)

        rows: list[dict[str, Any]] = []
        errors = 0
        for path in self.runs_dir.glob("*.json"):
            try:
                rows.append(self._summary(self._load(path)))
            except HistoryNotFound:
                errors += 1

        rows.sort(
            key=lambda row: (row["created_at"], row["run_id"]),
            reverse=True,
        )
        return HistoryListResult(rows, errors)
