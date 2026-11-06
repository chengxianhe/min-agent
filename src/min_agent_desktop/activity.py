"""Read only allowlisted public tool events from one explicitly attached transcript."""
from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime

from .sanitize import clean_text, display_output


def timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def public_text(content):
    if isinstance(content, str):
        return clean_text(content, 800)
    if isinstance(content, list):
        return clean_text("\n".join(x.get("text", "") for x in content if isinstance(x, dict)
                                     and x.get("type") in {"Text", "text", "output_text"}), 800)
    return ""


class ActivityReader:
    def __init__(self, thread_id, since):
        self.thread_id = thread_id
        self.since = since
        self.calls = OrderedDict()
        self.pending = OrderedDict()
        self.commentary = ""
        self.last_event_at = 0.0
        self.turn_active = False

    def consume(self, record):
        at = timestamp(record.get("timestamp"))
        if at < self.since:
            return
        payload = record.get("payload", {})
        if not isinstance(payload, dict):
            return
        kind = payload.get("type")
        if record.get("type") == "response_item":
            # Only outer tool envelope metadata. Never display script bodies or reasoning.
            call_id = payload.get("call_id")
            if kind in {"function_call", "custom_tool_call"} and call_id:
                self.pending[call_id] = {"id": str(call_id), "name": clean_text(payload.get("name"), 120), "started_at": at}
                while len(self.pending) > 16:
                    self.pending.popitem(last=False)
                self.turn_active = True
            elif kind in {"function_call_output", "custom_tool_call_output"}:
                self.pending.pop(call_id, None)
            else:
                return
            self.last_event_at = at
            return
        if record.get("type") != "event_msg":
            return
        if kind in {"task_started", "task_complete", "turn_aborted"}:
            self.turn_active = kind == "task_started"
            if not self.turn_active:
                self.pending.clear()
            self.last_event_at = at
            return
        if kind != "item_completed" or payload.get("thread_id") != self.thread_id:
            return
        item = payload.get("item", {})
        if not isinstance(item, dict):
            return
        item_type = item.get("type")
        if item_type == "AgentMessage" and item.get("phase") == "commentary":
            self.commentary = public_text(item.get("content"))
            self.last_event_at = at
            return
        if item_type not in {"CommandExecution", "McpToolCall", "FileChange", "Extension"}:
            return
        if item_type == "Extension" and not str(item.get("kind", "")).startswith("web."):
            return
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier:
            return
        status = {"completed": "completed", "failed": "failed", "declined": "denied",
                  "denied": "denied", "inProgress": "running"}.get(item.get("status"), "recorded")
        if item_type == "CommandExecution":
            name, parameters = "执行命令", item.get("command", "")
            result = item.get("aggregated_output", "")
            code = item.get("exit_code")
            if isinstance(code, int):
                status = "completed" if code == 0 else "failed"
                result = f"退出码：{code}\n{result}"
        elif item_type == "McpToolCall":
            name = f"{item.get('server', 'MCP')} / {item.get('tool', 'tool')}"
            parameters, result = item.get("arguments", {}), item.get("result", {})
            if isinstance(result, dict) and result.get("isError") is True:
                status = "failed"
        elif item_type == "FileChange":
            name = "修改文件"
            changes = item.get("changes", {})
            parameters = list(changes.keys()) if isinstance(changes, dict) else "文件变更"
            result = item.get("stdout") or item.get("stderr") or "文件变更已记录；不展示文件正文。"
        else:
            name = "网页工具 / " + str(item.get("kind"))
            parameters = item.get("query") or item.get("action") or "网页请求"
            result = "已记录网页工具返回；完整资料请在聊天中查看。"
        duration = item.get("duration")
        seconds = None
        if isinstance(duration, dict):
            seconds = max(0, duration.get("secs", 0) + duration.get("nanos", 0) / 1e9)
        elif isinstance(payload.get("started_at_ms"), (int, float)) and isinstance(payload.get("completed_at_ms"), (int, float)):
            seconds = max(0, (payload["completed_at_ms"] - payload["started_at_ms"]) / 1000)
        self.calls[identifier] = {"id": identifier, "name": clean_text(name, 120), "status": status,
                                  "time": at, "duration": seconds,
                                  "parameters": clean_text(parameters, 900),
                                  "result": display_output(parameters, result)}
        self.calls.move_to_end(identifier)
        while len(self.calls) > 20:
            self.calls.popitem(last=False)
        self.last_event_at = at

    def snapshot(self, checked_at, error=""):
        return {"version": 1, "thread_id": self.thread_id, "checked_at": checked_at,
                "last_event_at": self.last_event_at, "error": error,
                "turn_active": self.turn_active, "commentary": self.commentary,
                "pending": list(self.pending.values()), "calls": list(self.calls.values())}
