import json
from pathlib import Path
import socket
import struct
import tempfile
import time
import unittest

from min_agent_wechat.current_session import CurrentSession, SessionUnavailable
from min_agent_wechat.card_binding import register_connection
from min_agent_wechat.files import save_json
from min_agent_wechat.local_socket import LocalSocket, RpcError, TransportError
from min_agent_wechat.relay_mirror import mirror, snapshot, command_reply
from min_agent_wechat.relay_service import deliver
from min_agent_wechat.relay_store import RelayStore


class FakeConnection:
    def __init__(self, status="active", fail=None, accepts=True):
        self.calls, self.status, self.fail, self.accepts = [], status, fail, accepts

    def call(self, method, params):
        self.calls.append((method, params))
        if method == "thread/read":
            return {"thread": {"id": "thread-1", "canAcceptDirectInput": self.accepts,
                               "status": {"type": self.status, "activeFlags": []}}}
        if method == "thread/turns/list":
            return {"data": [{"id": "turn-1", "status": "inProgress"}]}
        if self.fail:
            raise self.fail
        return {"turnId": "turn-1"} if method == "turn/steer" else {"turn": {"id": "turn-2"}}

    def close(self):
        pass


class SessionTests(unittest.TestCase):
    def test_active_uses_existing_turn_and_never_overrides_authority(self):
        connection = FakeConnection()
        session = CurrentSession("unused", "thread-1")
        method, params = session.prepare(connection, "继续刚才的任务", "123")
        self.assertEqual(method, "turn/steer")
        self.assertEqual(params["expectedTurnId"], "turn-1")
        self.assertEqual(set(params), {"threadId", "expectedTurnId", "clientUserMessageId", "input"})
        self.assertIn("继续刚才的任务", params["input"][0]["text"])
        self.assertEqual(connection.calls[1][1]["itemsView"], "notLoaded")

    def test_idle_starts_next_turn_in_same_thread(self):
        method, params = CurrentSession("unused", "thread-1").prepare(FakeConnection("idle"), "继续", "123")
        self.assertEqual(method, "turn/start")
        self.assertEqual(params["threadId"], "thread-1")
        self.assertEqual(set(params), {"threadId", "clientUserMessageId", "input"})

    def test_unloaded_or_input_disallowed_is_not_resumed_or_forked(self):
        for connection in [FakeConnection("notLoaded"), FakeConnection(accepts=False)]:
            with self.assertRaises(SessionUnavailable):
                CurrentSession("unused", "thread-1").prepare(connection, "test", "1")
            self.assertEqual([m for m, _ in connection.calls], ["thread/read"])


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = RelayStore(self.root, "owner", "thread-1", since=time.time() - 10)
        save_json(self.root / "activity-source.json", {"thread_id": "thread-1"})

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def ingest(self, identity="1", text="继续", **changes):
        msg = {"message_id": identity, "from_user_id": "owner", "message_type": 1,
               "create_time_ms": time.time() * 1000, "context_token": "private-context",
               "item_list": [{"type": 1, "text_item": {"text": text}}], **changes}
        self.store.ingest({"msgs": [msg], "get_updates_buf": "cursor-next"})

    def test_dedup_and_cursor_commit_together(self):
        self.ingest()
        self.ingest()
        self.assertEqual(self.store.summary()["tasks"], {"queued": 1})
        self.assertEqual(self.store.get("cursor"), "cursor-next")

    def test_foreign_group_old_or_contextless_messages_do_not_enter_queue(self):
        self.ingest(from_user_id="stranger")
        self.ingest(group_id="group")
        self.ingest(create_time_ms=1)
        self.ingest(context_token="")
        self.assertIsNone(self.store.next_message())
        self.assertEqual(self.store.get("context"), "")

    def test_queue_and_message_limits(self):
        self.ingest(text="x" * 8001)
        for n in range(2, 25):
            self.ingest(str(n))
        self.assertEqual(self.store.summary()["tasks"], {"queued": 20, "rejected": 4})

    def test_binding_cannot_silently_change(self):
        with self.assertRaises(ValueError):
            RelayStore(self.root, "owner", "other-thread")

    def test_successful_dispatch_records_turn_without_spawning_executor(self):
        self.ingest()
        connection = FakeConnection()
        session = CurrentSession("unused", "thread-1", lambda _: connection)
        deliver(self.store, session, self.store.next_message(), self.root)
        self.assertEqual(self.store.summary()["tasks"], {"delivered": 1})
        self.assertEqual(connection.calls[-1][0], "turn/steer")
        self.assertEqual(self.store.db.execute("SELECT turn_id FROM inbox").fetchone()[0], "turn-1")
        self.ingest()
        self.assertIsNone(self.store.next_message())

    def test_lost_ack_is_uncertain_and_never_automatically_replayed(self):
        self.ingest()
        session = CurrentSession("unused", "thread-1", lambda _: FakeConnection(fail=TimeoutError()))
        deliver(self.store, session, self.store.next_message(), self.root)
        self.assertEqual(self.store.summary()["tasks"], {"uncertain": 1})
        self.ingest()
        self.assertIsNone(self.store.next_message())

    def test_explicit_server_rejection_has_truthful_receipt(self):
        self.ingest()
        session = CurrentSession("unused", "thread-1", lambda _: FakeConnection(fail=RpcError(-32600)))
        deliver(self.store, session, self.store.next_message(), self.root)
        self.assertEqual(self.store.summary()["tasks"], {"rejected": 1})
        self.assertIn("没有转发成功", self.store.outgoing()["text"])

    def test_unavailable_before_send_stays_queued(self):
        self.ingest()
        session = CurrentSession("unused", "thread-1", lambda _: FakeConnection("notLoaded"))
        with self.assertRaises(SessionUnavailable):
            deliver(self.store, session, self.store.next_message(), self.root)
        self.assertEqual(self.store.summary()["tasks"], {"queued": 1})

    def test_restart_marks_inflight_uncertain_and_keeps_reply(self):
        self.ingest()
        self.store.mark("1", "sending")
        self.store.db.close()
        self.store = RelayStore(self.root, "owner", "thread-1")
        self.assertEqual(self.store.summary()["tasks"], {"uncertain": 1})
        self.assertIn("不会自动重发", self.store.outgoing()["text"])

    def test_card_binding_switch_blocks_dispatch(self):
        self.ingest()
        save_json(self.root / "activity-source.json", {"thread_id": "other"})
        connection = FakeConnection()
        with self.assertRaises(ValueError):
            deliver(self.store, CurrentSession("unused", "thread-1", lambda _: connection),
                    self.store.next_message(), self.root)
        self.assertEqual(connection.calls, [])

    def test_outgoing_uses_latest_context_without_exposing_it(self):
        self.ingest()
        with self.store.lock, self.store.db:
            self.store.enqueue("note:one", "token=secret-value 测试")
        self.ingest("2", context_token="new-context")
        self.assertEqual(self.store.get("context"), "new-context")
        self.assertNotIn("secret-value", self.store.outgoing()["text"])
        self.assertNotIn("private-context", self.store.outgoing()["text"])

    def test_note_dedup_and_old_notes_not_replayed(self):
        state = {"task_id": "task", "title": "工作", "status": "running", "action": "进行中"}
        feed = {"turn_active": True, "notes": [
            {"id": "old", "time": 1, "kind": "final", "text": "历史回复"},
            {"id": "new", "time": time.time(), "kind": "commentary", "text": "公开说明"}]}
        mirror(self.store, state, feed)
        mirror(self.store, state, feed)
        rows = self.store.db.execute("SELECT id FROM outbox").fetchall()
        self.assertEqual(len(rows), 2)
        self.assertNotIn("note:old", [r[0] for r in rows])

    def test_final_is_not_delayed_or_followed_by_stale_commentary(self):
        state = {"task_id": "task", "title": "工作", "status": "succeeded", "action": "结束"}
        now = time.time()
        feed = {"notes": [{"id": "c", "time": now - 1, "kind": "commentary", "text": "检查中"},
                          {"id": "f", "time": now, "kind": "final", "text": "完成"}]}
        mirror(self.store, state, feed)
        rows = [r[0] for r in self.store.db.execute("SELECT id FROM outbox")]
        self.assertIn("note:f", rows)
        self.assertNotIn("note:c", rows)

    def test_snapshot_rejects_stale_or_wrong_thread_feed(self):
        save_json(self.root / "state.json", {"task_id": "task"})
        save_json(self.root / "activity-heartbeat.json", {"thread_id": "thread-1", "checked_at": time.time()})
        save_json(self.root / "activity.json", {"thread_id": "other"})
        with self.assertRaises(ValueError):
            snapshot(self.root, "thread-1")
        save_json(self.root / "activity.json", {"thread_id": "thread-1"})
        save_json(self.root / "activity-heartbeat.json", {"thread_id": "thread-1", "checked_at": 1})
        with self.assertRaises(ValueError):
            snapshot(self.root, "thread-1")

    def test_native_card_registration_exposes_directory_only(self):
        card = self.root / "card"
        register_connection(card, self.root)
        binding = json.loads((card / "wechat-source.json").read_text())
        self.assertEqual(binding, {"version": 1, "directory": str(self.root.resolve())})
        self.assertEqual((card / "wechat-source.json").stat().st_mode & 0o777, 0o600)


class FrameTests(unittest.TestCase):
    def setUp(self):
        a, self.peer = socket.socketpair()
        self.client = LocalSocket.__new__(LocalSocket)
        self.client.socket, self.client.timeout = a, 1

    def tearDown(self):
        self.client.close()
        self.peer.close()

    def test_client_masks_frames(self):
        self.client._send(b"hello")
        raw = self.peer.recv(100)
        self.assertEqual(raw[0], 129)
        self.assertEqual(raw[1], 128 + 5)
        self.assertEqual(bytes(v ^ raw[2 + i % 4] for i, v in enumerate(raw[6:])), b"hello")

    def test_fragmented_json_with_interleaved_ping(self):
        self.peer.sendall(b'\x01\x05{"x":' + b'\x89\x01p' + b'\x80\x021}')
        self.assertEqual(self.client._receive(time.monotonic() + 1), {"x": 1})
        self.assertEqual(self.peer.recv(100)[0], 138)

    def test_oversized_response_is_rejected_before_allocating_body(self):
        self.peer.sendall(b'\x81\x7f' + struct.pack('!Q', 8 * 1024 * 1024))
        with self.assertRaises(TransportError):
            self.client._receive(time.monotonic() + 1)

    def test_masked_server_frame_and_close_are_rejected(self):
        self.peer.sendall(b'\x81\x80')
        with self.assertRaises(TransportError):
            self.client._receive(time.monotonic() + 1)


if __name__ == "__main__":
    unittest.main()
