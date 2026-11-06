from __future__ import annotations

import fcntl
import json
import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

STATUSES = {"running", "waiting", "succeeded", "failed"}
TERMINAL = {"succeeded", "failed"}
MAX_BYTES = 65536


def default_directory() -> Path:
    return Path.home() / "Library/Application Support/AgentProgressCard"


def checked_text(value: str, name: str, limit: int, required: bool = True) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{name} 不能为空")
    if len(value) > limit:
        raise ValueError(f"{name} 最多 {limit} 个字符")
    return value.strip()


class ProgressStore:
    """One foreground task; atomic writes and task identity guard concurrent writers."""

    def __init__(self, directory: Path | None = None):
        self.directory = directory if directory is not None else default_directory()
        self.path = self.directory / "state.json"

    def read(self) -> dict | None:
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(MAX_BYTES + 1)
        except FileNotFoundError:
            return None
        if len(raw) > MAX_BYTES:
            raise ValueError("状态文件过大")
        data = json.loads(raw)
        if not isinstance(data, dict) or data.get("version") != 1:
            raise ValueError("不支持的状态文件")
        if data.get("status") not in STATUSES or not isinstance(data.get("events"), list):
            raise ValueError("状态文件损坏")
        return data

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.directory / "state.lock", os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def _save(self, state: dict) -> dict:
        raw = json.dumps(state, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(raw) > MAX_BYTES:
            raise ValueError("状态文件过大")
        descriptor, name = tempfile.mkstemp(prefix=".state-", dir=self.directory)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return state

    def begin(self, title: str, action: str, replace: bool = False) -> dict:
        title = checked_text(title, "任务名称", 80)
        action = checked_text(action, "当前动作", 160)
        with self._locked():
            current = self.read()
            if current and current["status"] not in TERMINAL and not replace:
                raise ValueError("已有任务；请更新原任务，或明确使用 --replace 切换显示的任务")
            now = time.time()
            event = {"id": str(uuid.uuid4()), "time": now, "action": action,
                     "detail": "", "status": "running"}
            return self._save({"version": 1, "task_id": str(uuid.uuid4()), "title": title,
                               "status": "running", "action": action, "detail": "",
                               "updated_at": now, "events": [event]})

    def update(self, task_id: str, status: str, action: str, detail: str = "") -> dict:
        if status not in STATUSES:
            raise ValueError("无效状态")
        action = checked_text(action, "当前动作", 160)
        detail = checked_text(detail, "说明", 1000, required=False)
        with self._locked():
            current = self.read()
            if not current or current["task_id"] != task_id:
                raise ValueError("任务已切换或不存在，拒绝旧任务覆盖")
            if current["status"] in TERMINAL:
                raise ValueError("任务已结束；请用 begin 开始新任务")
            now = time.time()
            current.update(status=status, action=action, detail=detail, updated_at=now)
            current["events"] = (current["events"] + [
                {"id": str(uuid.uuid4()), "time": now, "action": action,
                 "detail": detail, "status": status}
            ])[-8:]
            return self._save(current)
