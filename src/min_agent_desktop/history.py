"""Bounded local task archive. Explicit task IDs, never inferred from chat text."""
import fcntl
import json
import os
import tempfile
from pathlib import Path

from .sanitize import clean_text

MAX_BYTES = 4 * 1024 * 1024
MAX_TASKS = 12


def read_history(directory):
    path = Path(directory) / "history.json"
    if not path.exists():
        return {"version": 1, "tasks": []}
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("任务历史过大")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("tasks"), list):
        raise ValueError("任务历史格式无效")
    if len(data["tasks"]) > MAX_TASKS:
        raise ValueError("任务历史超出数量限制")
    return data


def update_history(directory, state, feed=None):
    """Caller holds state.lock. A second lock protects archive readers/writers."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(directory / "history.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        history = read_history(directory)
        previous = json.dumps(history, ensure_ascii=False)
        tasks = history["tasks"]
        task = next((x for x in tasks if x["task_id"] == state["task_id"]), None)
        if task is None:
            task = {"task_id": state["task_id"], "calls": [], "steps": [], "thread_id": "",
                    "started_at": state.get("started_at", state["updated_at"]),
                    "legacy": "started_at" not in state}
            tasks.append(task)
        for key, limit in (("title", 80), ("action", 160), ("detail", 1000)):
            task[key] = clean_text(state.get(key, ""), limit)
        task["status"] = state["status"]
        task["updated_at"] = state["updated_at"]
        start = task["started_at"]
        end = state["updated_at"] if state["status"] in {"succeeded", "failed"} else float("inf")
        steps = {x["id"]: x for x in task["steps"]}
        for event in state.get("events", []):
            steps["state:" + event["id"]] = {"id": "state:" + event["id"], "time": event["time"],
                "text": clean_text("\n".join(filter(None, [event["action"], event.get("detail")])), 1000),
                "kind": "progress"}
        if feed and not feed.get("error") and feed.get("thread_id"):
            thread = feed["thread_id"]
            if task["thread_id"] and task["thread_id"] != thread:
                raise ValueError("此任务已绑定其他会话；请新建任务后切换")
            task["thread_id"] = thread
            calls = {x["id"]: x for x in task["calls"]}
            for call in feed.get("calls", []):
                if start <= call.get("started_at", call["time"]) <= call["time"] <= end:
                    calls[call["id"]] = call
            task["calls"] = sorted(calls.values(), key=lambda x: (x["time"], x["id"]))[-20:]
            for note in feed.get("notes", []):
                if start <= note["time"] <= end:
                    steps["note:" + note["id"]] = {**note, "id": "note:" + note["id"]}
        task["steps"] = sorted(steps.values(), key=lambda x: (x["time"], x["id"]))[-30:]
        history["tasks"] = tasks[-MAX_TASKS:]
        raw = json.dumps(history, ensure_ascii=False, allow_nan=False)
        while len(raw.encode()) > MAX_BYTES and len(history["tasks"]) > 1:
            history["tasks"].pop(0)
            raw = json.dumps(history, ensure_ascii=False, allow_nan=False)
        if len(raw.encode()) > MAX_BYTES:
            raise ValueError("任务历史超出大小限制")
        if raw == previous:
            return
        fd, temporary = tempfile.mkstemp(prefix=".history-", dir=directory)
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(raw)
            os.replace(temporary, directory / "history.json")
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
