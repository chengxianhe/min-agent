"""Forward only the already-sanitized card surface belonging to the bound thread."""
import hashlib
import json
import time

from min_agent_desktop.sanitize import clean_text
from .files import read_json


def check_binding(directory, thread_id):
    if read_json(directory / "activity-source.json").get("thread_id") != thread_id:
        raise ValueError("小看板已切换会话；停止转发，避免串台")


def snapshot(directory, thread_id):
    check_binding(directory, thread_id)
    feed = read_json(directory / "activity.json")
    heartbeat = read_json(directory / "activity-heartbeat.json")
    if (feed.get("thread_id") != thread_id or heartbeat.get("thread_id") != thread_id
            or feed.get("error") or time.time() - heartbeat.get("checked_at", 0) > 20):
        raise ValueError("当前会话的小看板记录尚未就绪")
    state = read_json(directory / "state.json")
    if state.get("source") == "wechat":
        raise ValueError("小看板仍显示旧版独立任务，请切回当前会话")
    return state, feed


def overview(state, feed):
    notes = [x for x in feed.get("notes", []) if x.get("kind") == "commentary"]
    explanation = notes[-1].get("text", "") if notes else state.get("detail") or state.get("action")
    pending = feed.get("pending", [])
    tool = "\n当前工具：" + clean_text(pending[-1].get("name"), 120) if pending else ""
    return clean_text("当前任务：" + state.get("title", "当前会话") + "\n"
                      + ("执行中" if feed.get("turn_active") else "等待下一条消息")
                      + "\n" + str(explanation or "暂无新的工作说明") + tool, 1600)


def command_reply(text, state, feed):
    if text in ("帮助", "/help"):
        return ("已连接你指定的桌面会话。普通文字会作为你的消息送入该会话，保留上下文。\n"
                "进度：查看小看板当前进度\n结果：查看最近公开回复\n"
                "权限审批仍在原客户端处理；不会自动同意审批。")
    if text in ("进度", "/status"):
        return overview(state, feed)
    if text in ("结果", "/result"):
        notes = [x for x in feed.get("notes", []) if x.get("kind") == "final"]
        return "最近公开回复：\n" + (notes[-1]["text"] if notes else "当前没有已记录的最终回复。")
    return None


def mirror(store, state, feed):
    """Dedup by public note ID; commentary is throttled, final responses are not."""
    since = float(store.get("since"))
    now = time.time()
    with store.lock, store.db:
        commentary = [n for n in feed.get("notes", []) if n.get("kind") == "commentary" and n.get("time", 0) >= since]
        finals = [n for n in feed.get("notes", []) if n.get("kind") == "final" and n.get("time", 0) >= since]
        candidates = list(finals)
        if commentary and now - float(store.get("last_progress", "0")) >= 20:
            latest = commentary[-1]
            # Don't send a delayed commentary after a later final reply.
            if not finals or latest["time"] > finals[-1]["time"]:
                candidates.append(latest)
        for note in sorted(candidates, key=lambda x: x["time"]):
            key = "note:" + str(note["id"])
            if store.db.execute("SELECT 1 FROM outbox WHERE id=?", (key,)).fetchone():
                continue
            label = "当前会话回复" if note["kind"] == "final" else "当前工作说明"
            store.enqueue(key, label + "\n" + clean_text(note["text"], 1800))
            if note["kind"] == "commentary":
                store.db.execute("INSERT OR REPLACE INTO meta VALUES ('last_progress',?)", (str(now),))
        # Manual task status is useful even when there is no new assistant note.
        material = {k: state.get(k) for k in ("task_id", "title", "status", "action", "detail")}
        digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
        if store.get("card_digest") != digest:
            store.enqueue("card:" + digest, overview(state, feed))
            store.db.execute("INSERT OR REPLACE INTO meta VALUES ('card_digest',?)", (digest,))
