import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from min_agent_desktop.history import read_history
from min_agent_desktop.watcher import remote_snapshot
from min_agent_wechat.card import Card, recover_card
from min_agent_wechat.database import Database
from min_agent_wechat.executor import command, execute, public_event
from min_agent_wechat.files import read_json, save_json
from min_agent_wechat.ilink import BASE_URL, Client, LinkError, trusted_base
from min_agent_wechat.login import login


def message(identity=1, text="总结当前目录", **changes):
    return {"message_id": identity, "from_user_id": "owner", "message_type": 1,
            "context_token": "private-context", "create_time_ms": time.time() * 1000,
            "item_list": [{"type": 1, "text_item": {"text": text}}], **changes}


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Database(self.root, "owner", time.time())

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def ingest(self, *messages):
        self.store.ingest({"msgs": list(messages), "get_updates_buf": "next"})

    def test_duplicate_delivery_executes_once_and_cursor_persists(self):
        msg = message()
        self.ingest(msg, msg)
        self.ingest(msg)
        self.assertEqual(self.store.summary()["tasks"], {"queued": 1})
        self.assertEqual(self.store.cursor(), "next")
        task = self.store.claim()
        self.assertTrue(task)
        self.assertIsNone(self.store.claim())

    def test_foreign_group_bot_old_and_missing_identity_are_ignored(self):
        self.ingest(message(from_user_id="stranger"), message(2, group_id="group"),
                    message(3, message_type=2), message(4, create_time_ms=1),
                    message(None), message(5, context_token=""))
        self.assertEqual(self.store.summary(), {"tasks": {}, "unsent": 0})

    def test_commands_and_nontext_do_not_launch_tasks(self):
        self.ingest(message(text="帮助"), message(2, "进度"), message(3, "结果"), message(4, item_list=[]))
        self.assertEqual(self.store.summary(), {"tasks": {}, "unsent": 4})

    def test_queue_and_prompt_are_bounded(self):
        self.ingest(*[message(i + 1) for i in range(12)], message(20, "x" * 4001))
        self.assertEqual(self.store.summary()["tasks"], {"queued": 10})

    def test_crash_recovery_does_not_rerun(self):
        self.ingest(message())
        task = self.store.claim()
        self.store.recover()
        self.store.recover()
        self.assertIsNone(self.store.claim())
        row = self.store.db.execute("SELECT * FROM tasks").fetchone()
        self.assertEqual(row["status"], "interrupted")
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM outbox WHERE id LIKE ?",
                                             (task["id"] + ":final:%",)).fetchone()[0], 1)

    def test_cursor_and_message_commit_roll_back_together(self):
        with self.assertRaises(RuntimeError), patch.object(self.store, "_reply", side_effect=RuntimeError()):
            self.ingest(message())
        self.assertEqual(self.store.cursor(), "")
        self.assertEqual(self.store.summary()["tasks"], {})
        self.ingest(message())
        self.assertTrue(self.store.claim())

    def test_send_failure_is_retained_with_stable_id(self):
        self.ingest(message())
        first = self.store.pending()
        self.store.sent(first["id"], False)
        self.assertIsNone(self.store.pending())
        with self.store.db:
            self.store.db.execute("UPDATE outbox SET due=0")
        self.assertEqual(first["id"], self.store.pending()["id"])
        self.store.sent(first["id"], True)
        self.assertIsNone(self.store.pending())

    def test_result_parts_and_secret_redaction(self):
        self.ingest(message())
        task = self.store.claim()
        self.store.finish(task["id"], "succeeded", "token=private-token\n" + "好" * 7000)
        rows = self.store.db.execute("SELECT text FROM outbox WHERE id LIKE '%:final:%'").fetchall()
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(len(r[0]) <= 3500 for r in rows))
        self.assertNotIn("private-token", "".join(r[0] for r in rows))

    def test_database_owner_and_file_permissions(self):
        with self.assertRaises(ValueError):
            Database(self.root, "other", time.time())
        self.assertEqual(stat.S_IMODE((self.root / "bridge.sqlite3").stat().st_mode), 0o600)


class ProtocolTests(unittest.TestCase):
    def test_token_stays_on_trusted_https_origin(self):
        for url in ("http://ilinkai.weixin.qq.com", "https://weixin.qq.com.evil.test",
                    "https://evil.test", "https://user:pass@ilinkai.weixin.qq.com",
                    BASE_URL + ":9999", BASE_URL + "/path", BASE_URL + "?secret=yes"):
            with self.subTest(url=url), self.assertRaises((LinkError, ValueError)):
                trusted_base(url)
        self.assertEqual(trusted_base(BASE_URL + "/"), BASE_URL)

    def test_send_is_fixed_to_owner_and_original_context(self):
        requests = []
        client = Client({"base_url": BASE_URL, "owner": "owner", "token": "private-token"},
                        lambda *a, **kw: requests.append((a, kw)))
        client.send("test", "ctx", "stable")
        args, kwargs = requests[0]
        self.assertEqual(args[1], "sendmessage")
        self.assertEqual(args[2]["msg"]["to_user_id"], "owner")
        self.assertEqual(args[2]["msg"]["context_token"], "ctx")
        self.assertEqual(args[2]["msg"]["message_type"], 2)
        self.assertEqual(kwargs["token"], "private-token")

    def test_missing_owner_fails_closed(self):
        with self.assertRaises(LinkError):
            Client({"base_url": BASE_URL, "owner": "", "token": "x"})

    def test_login_requires_scanner_identity_and_private_storage(self):
        for owner in (None, "owner"):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                responses = iter([{"qrcode": "q", "qrcode_img_content": "payload"},
                                  {"status": "confirmed", "bot_token": "private-token", "ilink_bot_id": "bot",
                                   "ilink_user_id": owner, "baseurl": BASE_URL}])
                transport = lambda *a, **kw: next(responses)
                if owner is None:
                    with self.assertRaises(LinkError):
                        login(root, threading.Event(), transport)
                    self.assertFalse((root / "credentials.json").exists())
                else:
                    credentials = login(root, threading.Event(), transport)
                    self.assertEqual(credentials["owner"], "owner")
                    self.assertEqual(stat.S_IMODE((root / "credentials.json").stat().st_mode), 0o600)
                    self.assertNotIn("private-token", (root / "connection.json").read_text())
                    self.assertNotIn("payload", (root / "connection.json").read_text())

    def test_login_rejects_external_redirect(self):
        with tempfile.TemporaryDirectory() as temp:
            responses = iter([{"qrcode": "q", "qrcode_img_content": "payload"},
                              {"status": "scaned_but_redirect", "redirect_host": "evil.test"}])
            with self.assertRaises(LinkError):
                login(Path(temp), threading.Event(), lambda *a, **kw: next(responses))

    def test_atomic_private_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "state.json"
            save_json(path, {"test": True})
            self.assertEqual(read_json(path), {"test": True})
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


class ExecutorTests(unittest.TestCase):
    def test_readonly_fresh_session_no_shell_injection(self):
        argv = command("/bin/codex", "/tmp")
        self.assertIn("read-only", argv)
        self.assertIn('approval_policy="never"', argv)
        self.assertIn("--ignore-rules", argv)
        self.assertNotIn("resume", argv)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
        self.assertEqual(argv[-1], "-")

    def test_reasoning_and_unknown_types_never_export(self):
        for kind in ("reasoning", "mcp_tool_call", "user_message", "unknown"):
            self.assertIsNone(public_event({"type": "item.completed", "item": {"type": kind, "text": "secret"}}))

    def fake_binary(self, root, body):
        path = root / "fake-codex"
        path.write_text("#!/usr/bin/env python3\nimport json,sys,time\nsys.stdin.read()\n" + body)
        path.chmod(0o700)
        return path

    def test_exit_zero_without_completion_is_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = self.fake_binary(root, "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'fake'}}))\n")
            status, _ = execute(binary, root, "test", lambda _: None, threading.Event(), timeout=3)
            self.assertEqual(status, "failed")

    def test_success_requires_completed_event_and_message_and_zero_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = self.fake_binary(root, "print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'ok'}}))\nprint(json.dumps({'type':'turn.completed'}))\n")
            status, result = execute(binary, root, "test", lambda _: None, threading.Event(), timeout=3)
            self.assertEqual((status, result), ("succeeded", "ok"))

    def test_timeout_terminates_process(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = self.fake_binary(root, "time.sleep(20)\n")
            start = time.monotonic()
            status, _ = execute(binary, root, "test", lambda _: None, threading.Event(), timeout=0.2)
            self.assertEqual(status, "failed")
            self.assertLess(time.monotonic() - start, 5)

    def test_stop_interrupts_instead_of_completing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = self.fake_binary(root, "time.sleep(20)\n")
            stop = threading.Event()
            stop.set()
            status, _ = execute(binary, root, "test", lambda _: None, stop, timeout=3)
            self.assertEqual(status, "interrupted")

    def test_card_history_is_bound_to_remote_task(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            card = Card(root, {"id": "task1", "prompt": "查看项目"})
            card.event({"kind": "tool", "id": "tool1", "name": "读取", "status": "running",
                        "parameters": "pwd", "result": ""})
            card.event({"kind": "tool", "id": "tool1", "name": "读取", "status": "succeeded",
                        "parameters": "pwd", "result": "完成"})
            card.finish("succeeded", "结果")
            task = read_history(root)["tasks"][0]
            self.assertEqual(task["thread_id"], "wechat-task1")
            self.assertEqual(len(task["calls"]), 1)
            self.assertEqual(remote_snapshot(root, card.state)["thread_id"], "wechat-task1")
            save_json(root / "wechat-activity.json", {"thread_id": "wrong"})
            self.assertTrue(remote_snapshot(root, card.state)["error"])

    def test_restart_recovers_only_its_matching_card(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            card = Card(root, {"id": "task1", "prompt": "查看项目"})
            recover_card(root, ["other"])
            self.assertEqual(card.store.read()["status"], "running")
            recover_card(root, ["task1"])
            self.assertEqual(card.store.read()["status"], "failed")
            self.assertFalse(read_json(root / "wechat-activity.json")["turn_active"])

    def test_remote_heartbeat_staleness_is_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            card = Card(root, {"id": "task1", "prompt": "查看项目"})
            card.feed["checked_at"] = time.time() - 30
            save_json(root / "wechat-activity.json", card.feed)
            self.assertTrue(remote_snapshot(root, card.state)["error"])


if __name__ == "__main__":
    unittest.main()
