from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from min_agent.agent_loop import AgentLoop
from min_agent.context_builder import ContextBuilder
from min_agent.context_loader import ContextLoader
from min_agent.permission_broker import PermissionBroker, PermissionWaitCancelled
from min_agent.runtime_factory import build_tool_registry, build_web_decision_model
from min_agent.session_key_store import SessionKeyStore
from min_agent.trace_recorder import TraceRecorder, now_iso
from min_agent.types import AgentRunResult, TraceEvent


DecisionModelName = Literal["fake", "deepseek"]
ManagedRunStatus = Literal["running", "waiting_permission", "completed", "failed", "interrupted"]


@dataclass
class ManagedRun:
    run_id: str
    user_goal: str
    workspace: str
    decision_model: DecisionModelName
    status: ManagedRunStatus
    created_at: str
    finished_at: str | None
    result: AgentRunResult | None
    recorder: TraceRecorder
    thread: threading.Thread | None = None
    record_path: Path | None = None
    finalized: bool = False

    def to_public_dict(self, include_events: bool = True) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "user_goal": self.user_goal,
            "workspace": self.workspace,
            "decision_model": self.decision_model,
            "status": self.status,
            "active": self.status in ("running", "waiting_permission"),
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "result": self.result.to_dict() if self.result else None,
            "events": [event.to_dict() for event in self.recorder.history()] if include_events else [],
        }


@dataclass
class RunEventSubscription:
    run_id: str
    initial_events: list[TraceEvent]
    event_queue: queue.Queue[TraceEvent | None]
    close_callback: Callable[[], None]

    def close(self) -> None:
        self.close_callback()


class RunManager:
    def __init__(
        self,
        workspace: Path | str,
        runs_dir: Path | str,
        key_store: SessionKeyStore,
        permission_broker: PermissionBroker,
        *,
        step_delay_seconds: float = 0.4,
        deepseek_model: str = "deepseek-v4-flash",
        deepseek_base_url: str = "https://api.deepseek.com",
        model_timeout_seconds: float = 30.0,
        model_max_tokens: int = 1200,
    ) -> None:
        self.workspace = Path(workspace).resolve()
        self.runs_dir = Path(runs_dir)
        self.key_store = key_store
        self.permission_broker = permission_broker
        self.step_delay_seconds = step_delay_seconds
        self.deepseek_model = deepseek_model
        self.deepseek_base_url = deepseek_base_url
        self.model_timeout_seconds = model_timeout_seconds
        self.model_max_tokens = model_max_tokens
        self._lock = threading.Lock()
        self._current: ManagedRun | None = None
        self._subs: dict[str, set[queue.Queue[TraceEvent | None]]] = {}
        self._closing = False

    def service_state(self) -> str:
        with self._lock:
            if self._current and self._current.status == "waiting_permission":
                return "approval_required"
            if self._current and self._current.status == "running":
                return "busy"
            return "ready"

    def active_run_id(self) -> str | None:
        with self._lock:
            if self._current and self._current.status in ("running", "waiting_permission"):
                return self._current.run_id
            return None

    def has_active_deepseek_run(self) -> bool:
        with self._lock:
            return bool(
                self._current
                and self._current.decision_model == "deepseek"
                and self._current.status in ("running", "waiting_permission")
            )

    def current_snapshot(self, include_events: bool = True) -> dict[str, Any] | None:
        with self._lock:
            return self._current.to_public_dict(include_events) if self._current else None

    def start_run(self, goal: str, decision_model: str) -> dict[str, Any]:
        if not isinstance(goal, str):
            raise ValueError("Goal must be a string")
        goal = goal.strip()
        if not goal or len(goal) > 1000:
            raise ValueError("Goal must contain 1 to 1000 characters")
        if not isinstance(decision_model, str) or decision_model not in ("fake", "deepseek"):
            raise ValueError("Unknown decision model")

        with self._lock:
            if self._closing:
                raise RuntimeError("Service is closing")
            if self._current and self._current.status in ("running", "waiting_permission"):
                raise RuntimeError("active_run_conflict")

            key = self.key_store.require() if decision_model == "deepseek" else None
            recorder = TraceRecorder(goal, str(self.workspace), decision_model=decision_model)
            run = ManagedRun(
                run_id=recorder.run_id,
                user_goal=goal,
                workspace=str(self.workspace),
                decision_model=decision_model,
                status="running",
                created_at=recorder.started_at,
                finished_at=None,
                result=None,
                recorder=recorder,
            )
            self._current = run
            self._subs[run.run_id] = set()
            recorder.subscribe(lambda event: self._on_event(run, event))

            thread = threading.Thread(target=self._worker, args=(run, key), daemon=True)
            run.thread = thread
            thread.start()
            return run.to_public_dict()

    def _on_event(self, run: ManagedRun, event: TraceEvent) -> None:
        with self._lock:
            if event.phase == "permission_requested":
                run.status = "waiting_permission"
            elif event.phase == "permission_resolved" and event.output.get("approved"):
                run.status = "running"
            targets = list(self._subs.get(run.run_id, set()))

        for target in targets:
            target.put(event)

    def _worker(self, run: ManagedRun, key: str | None) -> None:
        try:
            model, error = build_web_decision_model(
                run.decision_model,
                api_key=key,
                deepseek_model=self.deepseek_model,
                deepseek_base_url=self.deepseek_base_url,
                model_timeout_seconds=self.model_timeout_seconds,
                model_max_tokens=self.model_max_tokens,
            )
            if error:
                raise RuntimeError(error)

            context_loader = ContextLoader(
                run.workspace,
                str(self.runs_dir),
                run.decision_model,
            )
            loop = AgentLoop(
                ContextBuilder(context_loader),
                model,
                build_tool_registry(self.workspace),
                run.recorder,
                run.workspace,
                step_delay_seconds=self.step_delay_seconds,
                permission_callback=lambda action, details: self.permission_broker.request(
                    run.run_id,
                    action,
                    details,
                ),
            )
            result = loop.run(run.user_goal)
            self._finalize(run, result, "completed" if result.success else "failed")
        except PermissionWaitCancelled:
            self._finalize(run, None, "interrupted")
        except Exception as exc:
            message = "运行时发生未预期错误，请查看本次 Trace。"
            run.recorder.emit(
                phase="run_failed",
                status="failed",
                title="运行时错误",
                reason=message,
                output={
                    "message": message,
                    "error_type": type(exc).__name__,
                },
            )
            self._finalize(
                run,
                AgentRunResult(message=message, success=False),
                "failed",
            )

    def _finalize(
        self,
        run: ManagedRun,
        result: AgentRunResult | None,
        status: ManagedRunStatus,
    ) -> None:
        with self._lock:
            if run.finalized:
                return
            run.finalized = True
            run.result = result
            run.status = status
            run.finished_at = now_iso()

        run.record_path = run.recorder.save(self.runs_dir, status=status)
        with self._lock:
            for target in self._subs.pop(run.run_id, set()):
                target.put(None)

    def subscribe(self, run_id: str) -> RunEventSubscription:
        with self._lock:
            if not self._current or self._current.run_id != run_id:
                raise LookupError("Run not found")
            target: queue.Queue[TraceEvent | None] = queue.Queue()
            self._subs[run_id].add(target)
            history = self._current.recorder.history()

        return RunEventSubscription(
            run_id,
            history,
            target,
            lambda: self._remove_sub(run_id, target),
        )

    def _remove_sub(self, run_id: str, target: queue.Queue[TraceEvent | None]) -> None:
        with self._lock:
            self._subs.get(run_id, set()).discard(target)

    def close(self) -> None:
        with self._lock:
            self._closing = True
            run = self._current
        self.permission_broker.cancel_pending()
        if run and run.thread:
            run.thread.join(2)
