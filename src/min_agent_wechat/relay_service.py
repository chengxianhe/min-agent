"""Current-session mode: durable incoming text -> same thread; card -> WeChat."""
import hashlib
import sqlite3
import threading
import time

from .current_session import CurrentSession, SessionUnavailable
from .files import save_json
from .ilink import Client, LinkError
from .local_socket import RpcError, TransportError
from .relay_mirror import check_binding, command_reply, mirror, snapshot
from .relay_store import RelayStore


def seed_previous_connection(store, directory, owner):
    """Reuse only this owner's last reply context/cursor; never replay old tasks."""
    path = directory / "bridge.sqlite3"
    if not path.exists() or store.get("legacy_seeded"):
        return
    old = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    try:
        saved = old.execute("SELECT value FROM meta WHERE key='owner'").fetchone()
        if not saved or saved[0] != owner:
            raise ValueError("微信绑定与旧记录不一致")
        context = old.execute("SELECT context FROM tasks ORDER BY created DESC LIMIT 1").fetchone()
        cursor = old.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()
        with store.lock, store.db:
            if context:
                store.db.execute("INSERT OR IGNORE INTO meta VALUES ('context',?)", (context[0],))
            if cursor:
                store.db.execute("INSERT OR IGNORE INTO meta VALUES ('cursor',?)", (cursor[0],))
            store.db.execute("INSERT OR REPLACE INTO meta VALUES ('legacy_seeded','1')")
    finally:
        old.close()


def deliver(store, session, message, directory):
    """Only mark sending immediately before the mutating RPC; uncertainty is terminal."""
    check_binding(directory, session.thread_id)
    if message["text"] in ("帮助", "/help", "进度", "/status", "结果", "/result"):
        state, feed = snapshot(directory, session.thread_id)
        store.mark(message["id"], "local", reply=command_reply(message["text"], state, feed))
        return
    connection = session.open()
    try:
        method, params = session.prepare(connection, message["text"], message["id"])
        store.mark(message["id"], "sending")
        try:
            result = connection.call(method, params)
            turn = result.get("turnId") if method == "turn/steer" else result.get("turn", {}).get("id")
            if not isinstance(turn, str) or not turn:
                raise TransportError("缺少投递回执")
        except RpcError:
            store.mark(message["id"], "rejected", reply="当前会话拒绝了这次投递；没有转发成功，请稍后重发。")
        except Exception:
            store.mark(message["id"], "uncertain", reply="消息投递回执丢失，可能已进入当前会话。为避免重复执行，不会自动重发，请先在桌面核对。")
        else:
            store.mark(message["id"], "delivered", turn, "已送入当前会话。" if method == "turn/start" else "已补充到当前正在执行的任务。")
    finally:
        connection.close()


def run_relay(directory, credentials, thread_id, socket_path, card_directory, stop):
    store = RelayStore(directory, credentials["owner"], thread_id)
    seed_previous_connection(store, directory, credentials["owner"])
    session = CurrentSession(socket_path, thread_id)
    client = Client(credentials)
    health, health_lock = {}, threading.RLock()

    def health_update(component, problem=""):
        with health_lock:
            health[component] = problem

    def publish():
        with health_lock:
            problems = [p for p in health.values() if p]
        save_json(directory / "connection.json", {"mode": "current_session", "thread_id": thread_id,
                  "status": "retrying" if problems else "connected", "message": "；".join(problems) if problems else
                  "已连接当前会话。微信文字会送入这段聊天，小看板进度会回传。", **store.summary()})

    def poller():
        while not stop.is_set():
            try:
                batch = client.updates(store.get("cursor"))
                if stop.is_set():
                    break
                store.ingest(batch)
                health_update("wechat")
                stop.wait(.5)
            except LinkError as error:
                health_update("wechat", str(error))
                if error.expired:
                    stop.set()
                else:
                    stop.wait(5)

    def sender():
        while not stop.is_set():
            item = store.outgoing()
            if not item:
                stop.wait(.5)
                continue
            try:
                wire_id = "relay_" + hashlib.sha256(item["id"].encode()).hexdigest()[:32]
                client.send(item["text"], store.get("context"), wire_id)
                store.sent(item["id"], True)
                health_update("send")
            except LinkError as error:
                store.sent(item["id"], False)
                health_update("send", str(error) + "，回复保留待发送")
                if error.expired:
                    stop.set()

    def guarded(target):
        try:
            target()
        except Exception:
            health_update(target.__name__, "转发服务异常，已停止；本机记录保留")
            stop.set()

    threads = [threading.Thread(target=guarded, args=(poller,)), threading.Thread(target=guarded, args=(sender,))]
    for thread in threads:
        thread.start()
    next_probe = 0
    try:
        while not stop.is_set():
            try:
                check_binding(card_directory, thread_id)
            except (OSError, ValueError, KeyError):
                health_update("binding", "小看板绑定变化，转发已停止")
                stop.set()
                break
            try:
                message = store.next_message()
                if message:
                    deliver(store, session, message, card_directory)
                    health_update("codex")
                    next_probe = time.monotonic() + 10
                elif time.monotonic() >= next_probe:
                    connection = session.open()
                    try:
                        thread = session.inspect(connection)
                        flags = thread["status"].get("activeFlags", [])
                        health_update("codex", "当前任务等待你在原客户端确认" if "waitingOnApproval" in flags else "")
                    finally:
                        connection.close()
                    next_probe = time.monotonic() + 10
            except (OSError, ValueError, KeyError, TransportError, RpcError, SessionUnavailable):
                health_update("codex", "当前会话暂不可投递；消息保留排队，请检查桌面会话")
                stop.wait(2)
            try:
                state, feed = snapshot(card_directory, thread_id)
                mirror(store, state, feed)
                health_update("card")
            except (OSError, ValueError, KeyError, TypeError):
                health_update("card", "当前会话的看板进度暂不可读")
            publish()
            stop.wait(.5)
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=40)
        publish()
        with health_lock:
            problems = [p for p in health.values() if p]
        save_json(directory / "connection.json", {"mode": "current_session", "thread_id": thread_id,
            "status": "stopped", "message": "转发已停止；" + ("；".join(problems) if problems else "当前 Codex 任务不受影响"),
            **store.summary()})
        store.db.close()
