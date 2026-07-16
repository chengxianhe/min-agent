from __future__ import annotations

import copy
import threading
import uuid
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Literal

from min_agent.types import AgentAction


PermissionStatus = Literal["pending", "approved", "rejected", "cancelled"]


class PermissionNotFound(RuntimeError):
    pass


class PermissionAlreadyResolved(RuntimeError):
    pass


class PermissionWaitCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class PermissionSnapshot:
    permission_id: str
    run_id: str
    tool_name: str
    reason: str
    args: dict[str, Any]
    preview: str
    details: dict[str, Any]
    requested_at: str
    status: PermissionStatus

    def to_public_dict(self) -> dict[str, Any]:
        data = {
            "permission_id": self.permission_id,
            "run_id": self.run_id,
            "tool_name": self.tool_name,
            "reason": self.reason,
            "requested_at": self.requested_at,
            "status": self.status,
        }
        if self.tool_name == "write_file":
            data.update(
                {
                    "path": self.args.get("path"),
                    "mode": self.args.get("mode"),
                    "preview": self.preview,
                }
            )
        elif self.tool_name == "run_command":
            data.update(
                {
                    key: self.details.get(key)
                    for key in ("command_id", "command", "workspace", "risk")
                }
            )
        return copy.deepcopy(data)


class PermissionBroker:
    """Blocks a worker until the current Web permission is resolved once."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._current: PermissionSnapshot | None = None
        self._resolved_permission_ids: deque[str] = deque(maxlen=256)

    def request(
        self,
        run_id: str,
        action: AgentAction,
        details: dict[str, Any],
    ) -> bool:
        with self._condition:
            if self._current and self._current.status == "pending":
                raise RuntimeError("A permission request is already pending")

            self._current = PermissionSnapshot(
                permission_id=uuid.uuid4().hex,
                run_id=run_id,
                tool_name=action.tool_name or "",
                reason=action.reason,
                args=copy.deepcopy(action.args),
                preview=str(action.args.get("content", ""))[:200],
                details=copy.deepcopy(details),
                requested_at=datetime.now(timezone.utc)
                .astimezone()
                .isoformat(timespec="seconds"),
                status="pending",
            )
            self._condition.notify_all()
            self._condition.wait_for(
                lambda: self._current is not None and self._current.status != "pending"
            )
            status = self._current.status

        if status == "cancelled":
            raise PermissionWaitCancelled("Permission wait cancelled")
        return status == "approved"

    def current(self) -> PermissionSnapshot | None:
        with self._condition:
            return copy.deepcopy(self._current)

    def resolve(self, permission_id: str, approved: bool) -> PermissionSnapshot:
        if not isinstance(approved, bool):
            raise ValueError("approved must be a boolean")

        with self._condition:
            if self._current is None or self._current.permission_id != permission_id:
                if permission_id in self._resolved_permission_ids:
                    raise PermissionAlreadyResolved("Permission request already resolved")
                raise PermissionNotFound("Permission request not found")
            if self._current.status != "pending":
                raise PermissionAlreadyResolved("Permission request already resolved")

            self._current = replace(
                self._current,
                status="approved" if approved else "rejected",
            )
            self._resolved_permission_ids.append(permission_id)
            self._condition.notify_all()
            return copy.deepcopy(self._current)

    def cancel_pending(self) -> None:
        with self._condition:
            if self._current and self._current.status == "pending":
                self._current = replace(self._current, status="cancelled")
                self._resolved_permission_ids.append(self._current.permission_id)
                self._condition.notify_all()
