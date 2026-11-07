"""An explicitly bound live thread; never create, fork, resume or change permissions."""
from .local_socket import LocalSocket


class SessionUnavailable(Exception):
    pass


class CurrentSession:
    def __init__(self, socket_path, thread_id, factory=LocalSocket):
        self.socket_path, self.thread_id, self.factory = socket_path, thread_id, factory

    def open(self):
        return self.factory(self.socket_path)

    def inspect(self, connection):
        thread = connection.call("thread/read", {"threadId": self.thread_id, "includeTurns": False})["thread"]
        state = thread.get("status", {})
        if (thread.get("id") != self.thread_id or thread.get("canAcceptDirectInput") is not True
                or state.get("type") not in ("active", "idle")):
            raise SessionUnavailable("请在桌面打开已绑定的原会话；不会另建聊天")
        return thread

    def prepare(self, connection, text, message_id):
        thread = self.inspect(connection)
        params = {"threadId": self.thread_id, "clientUserMessageId": "wechat-" + message_id,
                  "input": [{"type": "text", "text": "[来自本人微信的消息]\n" + text}]}
        if thread["status"]["type"] == "idle":
            return "turn/start", params
        result = connection.call("thread/turns/list", {"threadId": self.thread_id,
                                 "limit": 1, "sortDirection": "desc", "itemsView": "notLoaded"})
        turns = result.get("data", [])
        if not turns or turns[0].get("status") != "inProgress":
            raise SessionUnavailable("当前轮次正在切换，消息留在队列中等待")
        params["expectedTurnId"] = turns[0]["id"]
        return "turn/steer", params
