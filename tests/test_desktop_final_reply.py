import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from min_agent_desktop.activity import ActivityReader
from min_agent_desktop.history import read_history, update_history
from min_agent_desktop.store import ProgressStore
from min_agent_desktop.watcher import TranscriptTail
from min_agent_wechat.relay_mirror import command_reply, mirror
from min_agent_wechat.relay_store import RelayStore


def message(identity="reply", phase="final_answer", at=100, thread="fixture-thread", text="已推送测试提交"):
    return {"timestamp": datetime.fromtimestamp(at, timezone.utc).isoformat(), "type": "event_msg",
            "payload": {"type": "item_completed", "thread_id": thread, "turn_id": "fixture-turn",
                        "item": {"type": "AgentMessage", "id": identity, "phase": phase,
                                 "content": [{"type": "Text", "text": text}]}}}


class FinalReplyTests(unittest.TestCase):
    def test_real_phase_and_legacy_phase_are_public_final_notes(self):
        for phase in ("final", "final_answer"):
            with self.subTest(phase=phase):
                reader = ActivityReader("fixture-thread", 0)
                event = message(phase=phase, text="已完成 token=fake-private-value")
                reader.consume(event)
                reader.consume(event)
                feed = reader.snapshot(200)
                self.assertEqual(1, len(feed["notes"]))
                self.assertEqual("final", feed["latest_reply"]["kind"])
                self.assertNotIn("fake-private-value", json.dumps(feed))
                self.assertEqual("", feed["commentary"])

    def test_latest_reply_survives_commentary_window_and_updates_on_next_reply(self):
        reader = ActivityReader("fixture-thread", 0)
        reader.consume(message())
        for i in range(40):
            reader.consume(message(str(i), "commentary", at=101+i, text="正在检查"))
        feed = reader.snapshot(200)
        self.assertEqual(30, len(feed["notes"]))
        self.assertEqual("reply", feed["latest_reply"]["id"])
        self.assertIn("已推送测试提交", command_reply("结果", {}, feed))
        reader.consume(message("new-reply", at=150))
        self.assertEqual("new-reply", reader.snapshot(200)["latest_reply"]["id"])

    def test_private_other_thread_and_before_binding_messages_are_excluded(self):
        reader = ActivityReader("fixture-thread", 50)
        for event in (message(phase="analysis"), message(thread="other"), message(at=1)):
            reader.consume(event)
        self.assertIsNone(reader.snapshot(200)["latest_reply"])
        self.assertEqual([], reader.snapshot(200)["notes"])

    def test_late_reply_is_visible_without_reopening_or_mutating_completed_task(self):
        with tempfile.TemporaryDirectory() as raw:
            directory = Path(raw)
            store = ProgressStore(directory)
            state = store.begin("测试任务", "执行")
            ended = store.update(state["task_id"], "succeeded", "完成")
            reader = ActivityReader("fixture-thread", 0)
            reader.consume(message(at=ended["updated_at"]+1))
            feed = reader.snapshot(ended["updated_at"]+2)
            update_history(directory, ended, feed)
            task = read_history(directory)["tasks"][0]
            self.assertEqual("succeeded", task["status"])
            self.assertFalse(any(x["kind"] == "final" for x in task["steps"]))
            self.assertEqual("已推送测试提交", feed["latest_reply"]["text"])

    def test_collector_restart_restores_reply_but_does_not_rebroadcast_history(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "fixture.jsonl"
            source.write_text(json.dumps({"type": "session_meta", "payload": {"id": "fixture-thread"}})
                              + "\n" + json.dumps(message()) + "\n")
            tail = TranscriptTail(source, "fixture-thread", 0)
            tail.poll()
            feed = tail.reader.snapshot(200)
            self.assertTrue(feed["latest_reply"]["replayed"])
            relay = RelayStore(root / "relay", "fixture-owner", "fixture-thread", since=1)
            self.addCleanup(relay.db.close)
            state = {"title": "测试任务", "status": "running", "action": "检查"}
            mirror(relay, state, feed)
            self.assertEqual(0, relay.db.execute("SELECT count(*) FROM outbox WHERE id LIKE 'note:%'").fetchone()[0])
            tail.reader.consume(message("live", at=tail.reader.replay_before+1))
            mirror(relay, state, tail.reader.snapshot(200))
            mirror(relay, state, tail.reader.snapshot(200))
            rows = relay.db.execute("SELECT id FROM outbox WHERE id LIKE 'note:%'").fetchall()
            self.assertEqual(["note:live"], [x[0] for x in rows])

    def test_turn_complete_keeps_final_and_clears_running_state(self):
        reader = ActivityReader("fixture-thread", 0)
        reader.consume({"timestamp": "2026-01-01T00:00:00Z", "type": "event_msg",
                        "payload": {"type": "task_started"}})
        reader.consume(message())
        reader.consume({"timestamp": "2026-01-01T00:00:01Z", "type": "event_msg",
                        "payload": {"type": "task_complete"}})
        feed = reader.snapshot(200)
        self.assertFalse(feed["turn_active"])
        self.assertIsNotNone(feed["latest_reply"])
