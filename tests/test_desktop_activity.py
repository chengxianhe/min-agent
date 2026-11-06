import json
import tempfile
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

from min_agent_desktop.activity import ActivityReader
from min_agent_desktop.sanitize import clean_text, display_output
from min_agent_desktop.watcher import TranscriptTail, validate_source

THREAD = "00000000-0000-4000-8000-000000000001"
TIME = "2026-11-06T12:00:00Z"


def item(kind="CommandExecution", identifier="call1", **fields):
    return {"timestamp": TIME, "type": "event_msg", "payload": {
        "type": "item_completed", "thread_id": THREAD, "started_at_ms": 1000,
        "completed_at_ms": 2500,
        "item": {"type": kind, "id": identifier, "status": "completed", **fields}}}


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.reader = ActivityReader(THREAD, 0)

    def test_actual_command_output_duration_failure_and_deduplication(self):
        event = item(command="python3 -m unittest", aggregated_output="FAIL: regression", exit_code=1)
        self.reader.consume(event)
        self.reader.consume(event)
        calls = self.reader.snapshot(1)["calls"]
        self.assertEqual(1, len(calls))
        self.assertEqual("failed", calls[0]["status"])
        self.assertEqual(1.5, calls[0]["duration"])
        self.assertIn("退出码：1", calls[0]["result"])

    def test_reasoning_user_text_other_threads_and_old_turns_excluded(self):
        for kind in ["Reasoning", "UserMessage", "AgentMessage"]:
            self.reader.consume(item(kind, content="PRIVATE", raw_content="PRIVATE", phase="analysis"))
        self.reader.consume({"type": "response_item", "timestamp": TIME,
                             "payload": {"type": "reasoning", "summary": "PRIVATE"}})
        wrong = item(command="PRIVATE")
        wrong["payload"]["thread_id"] = "another-thread"
        self.reader.consume(wrong)
        self.assertNotIn("PRIVATE", json.dumps(self.reader.snapshot(1)))
        old = ActivityReader(THREAD, 9999999999)
        old.consume(item(command="old"))
        self.assertEqual([], old.snapshot(1)["calls"])

    def test_public_commentary_only(self):
        self.reader.consume(item("AgentMessage", content=[{"type": "Text", "text": "正在检查文件"}], phase="commentary"))
        self.assertEqual("正在检查文件", self.reader.commentary)
        self.reader.consume(item("AgentMessage", content="private", phase="analysis"))
        self.assertEqual("正在检查文件", self.reader.commentary)

    def test_pending_envelopes_never_show_javascript_input(self):
        self.reader.consume({"timestamp": TIME, "type": "response_item", "payload": {
            "type": "custom_tool_call", "call_id": "a", "name": "exec", "input": "PRIVATE_SCRIPT"}})
        self.assertEqual(1, len(self.reader.pending))
        self.assertNotIn("PRIVATE_SCRIPT", json.dumps(self.reader.snapshot(1)))
        self.reader.consume({"timestamp": TIME, "type": "response_item", "payload": {
            "type": "custom_tool_call_output", "call_id": "a", "output": "PRIVATE_OUTPUT"}})
        self.assertEqual([], self.reader.snapshot(1)["pending"])

    def test_mcp_error_and_file_paths_without_diff(self):
        self.reader.consume(item("McpToolCall", server="docs", tool="search", arguments={"q": "query"},
                                 result={"isError": True, "content": [{"text": "timeout"}]}))
        self.assertEqual("failed", self.reader.snapshot(1)["calls"][0]["status"])
        self.reader.consume(item("FileChange", "file1", changes={"a.swift": {"diff": "PRIVATE_CONTENT"}}))
        result = self.reader.snapshot(1)["calls"][-1]
        self.assertIn("a.swift", result["parameters"])
        self.assertNotIn("PRIVATE_CONTENT", json.dumps(result))

    def test_bounded_recent_calls_and_unknown_status_not_passed(self):
        for index in range(30):
            event = item("McpToolCall", str(index), server="test", tool="tool", result={})
            event["payload"]["item"]["status"] = "unknown-new-status"
            self.reader.consume(event)
        calls = self.reader.snapshot(1)["calls"]
        self.assertEqual(20, len(calls))
        self.assertEqual("recorded", calls[-1]["status"])

    def test_redaction_before_truncation(self):
        for text in ['API_KEY="verysecret"', "Authorization: Bearer verysecret", "token=verysecret",
                     '{"password":"verysecret"}', "https://user:verysecret@example.com/path"]:
            self.assertNotIn("verysecret", clean_text(text))
        self.assertNotIn("nested-secret", clean_text({"nested": {"access_token": "nested-secret"}}))
        self.assertNotIn("secret-file", display_output("cat ~/.env", "secret-file"))
        self.assertNotIn("secret-file", display_output(["cat", "~/.env"], "secret-file"))
        self.assertIn("已截断", clean_text("x" * 2000, 20))


class TranscriptTailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "session.jsonl"
        self.meta = {"type": "session_meta", "payload": {"id": THREAD}}
        self.path.write_text(json.dumps(self.meta) + "\n")
        self.tail = TranscriptTail(self.path, THREAD, 0)

    def test_partial_line_is_not_lost_and_completed_item_is_not_duplicated(self):
        raw = json.dumps(item(command="echo ok", aggregated_output="ok", exit_code=0))
        with self.path.open("a") as stream:
            stream.write(raw[:30])
        self.tail.poll()
        self.assertEqual([], self.tail.reader.snapshot(1)["calls"])
        with self.path.open("a") as stream:
            stream.write(raw[30:] + "\n")
        self.tail.poll()
        self.tail.poll()
        self.assertEqual(1, len(self.tail.reader.snapshot(1)["calls"]))

    def test_wrong_source_rejected_and_rotation_revalidated(self):
        with self.assertRaises(ValueError):
            validate_source(self.path, "different")
        self.tail.poll()
        replacement = self.path.with_suffix(".new")
        replacement.write_text(json.dumps({"type": "session_meta", "payload": {"id": "different"}}) + "\n")
        replacement.replace(self.path)
        with self.assertRaises(ValueError):
            self.tail.poll()

    def test_corrupt_and_oversized_records_do_not_block_following_valid_event(self):
        with self.path.open("a") as stream:
            stream.write("broken\n" + "x" * (2 * 1024 * 1024 + 20) + "\n")
            stream.write(json.dumps(item(command="echo done", exit_code=0)) + "\n")
        self.tail.poll()
        self.assertEqual(1, len(self.tail.reader.snapshot(1)["calls"]))

    def test_running_collector_tracks_new_events_and_does_not_rewrite_idle_payload(self):
        directory = Path(self.temp.name)
        (directory / "activity-source.json").write_text(json.dumps({"path": str(self.path),
            "thread_id": THREAD, "since": 0}))
        root = Path(__file__).resolve().parents[1]
        process = subprocess.Popen([sys.executable, "-m", "min_agent_desktop.watcher", "--state-dir", str(directory)],
                                   env={**os.environ, "PYTHONPATH": str(root / "src")},
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            feed_path = directory / "activity.json"
            deadline = time.monotonic() + 5
            while not feed_path.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(feed_path.exists())
            initial_mtime = feed_path.stat().st_mtime_ns
            time.sleep(1.2)
            self.assertEqual(initial_mtime, feed_path.stat().st_mtime_ns)
            with self.path.open("a") as stream:
                stream.write(json.dumps(item(command="echo result", exit_code=0, aggregated_output="ACTUAL_RESULT")) + "\n")
            deadline = time.monotonic() + 5
            feed = {}
            while time.monotonic() < deadline:
                feed = json.loads(feed_path.read_text())
                if feed.get("calls"):
                    break
                time.sleep(0.05)
            self.assertIn("ACTUAL_RESULT", feed["calls"][0]["result"])
            self.assertTrue((directory / "activity-heartbeat.json").exists())
        finally:
            process.terminate()
            process.wait(timeout=3)
