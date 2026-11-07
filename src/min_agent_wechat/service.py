"""Polling, a single executor, and durable outgoing replies."""
import threading
import time

from .card import Card, recover_card
from .database import Database
from .executor import execute
from .files import save_json
from .ilink import Client, LinkError


def serve(directory, credentials, workspace, binary, card_directory, stop):
    client = Client(credentials)
    database = Database(directory, credentials["owner"], credentials["bound_at"])
    recover_card(card_directory, database.recover())
    failure = []

    def display(status, message):
        save_json(directory / "connection.json", {"status": status, "message": message,
                  "workspace": str(workspace), **database.summary()})

    def worker():
        while not stop.is_set():
            task = database.claim()
            if not task:
                stop.wait(0.5)
                continue
            card = None
            last_note = [0.0]
            try:
                if card_directory:
                    card = Card(card_directory, task)

                def event(value):
                    if value["kind"] == "heartbeat":
                        if card:
                            card.publish()
                        return
                    if card:
                        card.event(value)
                    detail = value.get("text") or value.get("name", "执行中")
                    database.progress(task["id"], detail)
                    # At most one public intermediate message every 30 seconds.
                    if value["kind"] == "message" and time.monotonic() - last_note[0] >= 30:
                        with database.lock, database.db:
                            database._reply(task["context"], f"任务 {task['id']} · 进度\n{detail[:800]}")
                        last_note[0] = time.monotonic()

                status, result = execute(binary, workspace, task["prompt"], event, stop)
            except Exception:
                status, result = "failed", "本机任务执行异常，已停止；请检查服务状态后重试。"
            database.finish(task["id"], status, result)
            if card:
                try:
                    card.finish(status, result)
                except (OSError, ValueError):
                    display("error", "任务已结束，但看板更新失败；结果保存在本机任务记录中。")

    def sender():
        while not stop.is_set():
            item = database.pending()
            if not item:
                stop.wait(0.5)
                continue
            try:
                client.send(item["text"], item["context"], item["id"])
                database.sent(item["id"], True)
            except LinkError as error:
                database.sent(item["id"], False)
                display("error" if error.expired else "retrying", str(error) + "；尚未送达的回复保留在本机。")
                if error.expired:
                    failure.append(str(error) + "；登录已失效，请重新扫码连接。")
                    stop.set()

    def guarded(target):
        try:
            target()
        except Exception:
            failure.append("本机任务或消息处理异常，服务已停止；记录已保留。")
            stop.set()

    threads = [threading.Thread(target=guarded, args=(worker,), name="wechat-worker"),
               threading.Thread(target=guarded, args=(sender,), name="wechat-sender")]
    for thread in threads:
        thread.start()
    try:
        display("connected", "已连接。在微信里发文字任务，或发送“进度”“结果”。")
        while not stop.is_set():
            try:
                batch = client.updates(database.cursor())
                if stop.is_set():
                    break
                database.ingest(batch)
                display("connected", "已连接。任务和回复状态见下方；电脑需保持运行。")
                stop.wait(0.5)
            except LinkError as error:
                display("error" if error.expired else "retrying", str(error) + "；任务记录已保留。")
                if error.expired:
                    failure.append(str(error) + "；登录已失效，请重新扫码连接。")
                    stop.set()
                else:
                    stop.wait(5)
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=40)
        display("error" if failure else "stopped", failure[-1] if failure else
                "微信服务已停止。任务记录保留；尚未送达的回复会在服务恢复后重试。")
        database.db.close()
