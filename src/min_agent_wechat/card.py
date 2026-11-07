"""Publish remote task state without mixing it with the desktop chat transcript."""
import time
import uuid

from min_agent_desktop.history import update_history
from min_agent_desktop.sanitize import clean_text
from min_agent_desktop.store import ProgressStore
from .files import read_json, save_json


def recover_card(directory, identities):
    """A crashed executor must not leave a permanently running card."""
    if not directory:
        return
    store = ProgressStore(directory)
    with store._locked():
        state = store.read()
        if (not state or state.get("source") != "wechat"
                or state["task_id"] not in {"wechat-" + x for x in identities}
                or state["status"] not in ("running", "waiting")):
            return
        now = time.time()
        state.update(status="failed", action="服务重启，原任务已中断",
                     detail="没有自动重做；如需重试请重新发送任务。", updated_at=now)
        state["events"] = (state["events"] + [{"id": uuid.uuid4().hex, "time": now,
            "status": "failed", "action": state["action"], "detail": state["detail"]}])[-8:]
        feed_path = store.directory / "wechat-activity.json"
        try:
            feed = read_json(feed_path)
            if feed.get("thread_id") == state["task_id"]:
                feed.update(turn_active=False, pending=[], checked_at=now)
                save_json(feed_path, feed)
        except (OSError, ValueError, AttributeError):
            pass
        store._save(state)


class Card:
    def __init__(self, directory, task):
        self.store = ProgressStore(directory)
        self.identity = "wechat-" + task["id"]
        now = time.time()
        self.feed = {"version": 1, "thread_id": self.identity, "checked_at": now,
                     "last_event_at": now, "error": "", "turn_active": True,
                     "commentary": "微信任务已开始", "pending": [], "calls": [], "notes": []}
        self.state = {"version": 1, "task_id": self.identity, "title": "微信 · " + clean_text(task["prompt"], 60),
                      "source": "wechat", "status": "running", "action": "正在执行微信只读任务",
                      "detail": "", "started_at": now, "updated_at": now, "events": []}
        self.publish(begin=True)

    def publish(self, begin=False):
        now = time.time()
        self.feed["checked_at"] = now
        with self.store._locked():
            current = self.store.read()
            if not begin and (not current or current["task_id"] != self.identity):
                return  # A user-selected newer task must not be overwritten.
            if begin and current:
                update_history(self.store.directory, current)
            save_json(self.store.directory / "wechat-activity.json", self.feed)
            self.store._save(self.state)
            update_history(self.store.directory, self.state, self.feed)

    def event(self, event):
        now = time.time()
        self.state["updated_at"] = now
        self.feed["last_event_at"] = now
        if event["kind"] == "message":
            text = clean_text(event["text"], 800)
            self.feed["commentary"] = text
            self.state.update(action="处理微信任务", detail=text)
            self.feed["notes"] = (self.feed["notes"] + [
                {"id": uuid.uuid4().hex, "time": now, "kind": "commentary", "text": text}])[-30:]
        else:
            identity = event["id"]
            pending = next((p for p in self.feed["pending"] if p["id"] == identity), None)
            self.feed["pending"] = [p for p in self.feed["pending"] if p["id"] != identity]
            if event["status"] == "running":
                self.feed["pending"] = (self.feed["pending"] + [
                    {"id": identity, "name": event["name"], "started_at": now}])[-16:]
            else:
                start = pending["started_at"] if pending else now
                self.feed["calls"] = (self.feed["calls"] + [{
                    **event, "time": now, "started_at": start, "duration": now - start,
                    "category": "command"}])[-20:]
            self.state["action"] = event["name"]
        self.publish()

    def finish(self, status, result):
        now = time.time()
        self.state.update(status="succeeded" if status == "succeeded" else "failed",
                          action="微信任务完成" if status == "succeeded" else "微信任务未完成",
                          detail=clean_text(result, 900), updated_at=now)
        self.feed.update(turn_active=False, pending=[], last_event_at=now)
        self.feed["notes"] = (self.feed["notes"] + [{"id": uuid.uuid4().hex, "time": now,
                                "kind": "final", "text": clean_text(result, 900)}])[-30:]
        self.publish()
