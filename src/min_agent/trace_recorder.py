from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from min_agent.types import EventPhase, EventStatus, TraceEvent


Subscriber = Callable[[TraceEvent], None]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class TraceRecorder:
    def __init__(
        self,
        user_goal: str,
        workspace: str,
        run_id: str | None = None,
        decision_model: str | None = None,
    ) -> None:
        self.run_id = run_id or datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.user_goal = user_goal
        self.workspace = workspace
        self.decision_model = decision_model if decision_model in {"fake", "deepseek"} else "unknown"
        self.started_at = now_iso()
        self.ended_at: str | None = None
        self.events: list[TraceEvent] = []
        self._subscribers: list[Subscriber] = []
        self._lock = threading.Lock()

    def subscribe(self, subscriber: Subscriber) -> None:
        with self._lock:
            self._subscribers.append(subscriber)

    def history(self) -> list[TraceEvent]:
        with self._lock:
            return list(self.events)

    def emit(
        self,
        phase: EventPhase,
        status: EventStatus,
        title: str,
        reason: str = "",
        input: dict[str, Any] | None = None,
        output: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> TraceEvent:
        with self._lock:
            event = TraceEvent(
                run_id=self.run_id,
                step=len(self.events) + 1,
                timestamp=now_iso(),
                phase=phase,
                status=status,
                title=title,
                reason=reason,
                input=input or {},
                output=output or {},
                task_id=task_id,
            )
            self.events.append(event)
            subscribers = list(self._subscribers)

        for subscriber in subscribers:
            try:
                subscriber(event)
            except Exception:
                continue
        return event

    def next_step(self) -> int:
        """返回下一条事件将使用的 step，供运行时原子记录溯源。"""
        with self._lock:
            return len(self.events) + 1

    def save(self, runs_dir: Path | str, status: EventStatus) -> Path:
        self.ended_at = now_iso()
        output_dir = Path(runs_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{self.run_id}.json"
        with self._lock:
            events = [event.to_dict() for event in self.events]

        data = {
            "run_id": self.run_id,
            "status": status,
            "user_goal": self.user_goal,
            "workspace": self.workspace,
            "decision_model": self.decision_model,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "events": events,
        }
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
