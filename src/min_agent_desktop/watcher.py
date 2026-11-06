"""Incremental, bounded local reader. Exits with its parent app; never invokes tools."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from pathlib import Path

from .activity import ActivityReader
from .store import default_directory

MAX_LINE = 2 * 1024 * 1024


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".activity-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_source(path, thread_id):
    with path.open("rb") as stream:
        raw = stream.readline(MAX_LINE + 1)
    record = json.loads(raw)
    if record.get("type") != "session_meta" or record.get("payload", {}).get("id") != thread_id:
        raise ValueError("会话编号与记录不匹配")


class TranscriptTail:
    def __init__(self, path, thread_id, since):
        self.path = path
        self.thread_id = thread_id
        self.since = since
        self.offset = 0
        self.identity = None
        self.discarding = False
        self.reader = ActivityReader(thread_id, since)

    def poll(self):
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if identity != self.identity or stat.st_size < self.offset:
            validate_source(self.path, self.thread_id)
            self.reader = ActivityReader(self.thread_id, self.since)
            self.offset, self.identity, self.discarding = 0, identity, False
        with self.path.open("rb") as stream:
            stream.seek(self.offset)
            for _ in range(500):
                start = stream.tell()
                line = stream.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE or self.discarding:
                    self.discarding = not line.endswith(b"\n")
                    self.offset = stream.tell()
                    continue
                if not line.endswith(b"\n"):
                    self.offset = start
                    break
                self.offset = stream.tell()
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        self.reader.consume(value)
                except (ValueError, TypeError, KeyError, AttributeError):
                    continue


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, default=default_directory())
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    parent = os.getppid()
    tail = None
    binding = None
    last_content = None
    while args.once or os.getppid() == parent:
        try:
            config = json.loads((args.state_dir / "activity-source.json").read_text())
            if config != binding:
                tail = TranscriptTail(Path(config["path"]), config["thread_id"], config["since"])
                binding = config
            tail.poll()
            if args.once:
                for _ in range(100):
                    previous = tail.offset
                    tail.poll()
                    if tail.offset == previous:
                        break
            snapshot = tail.reader.snapshot(time.time())
        except (OSError, ValueError, KeyError, TypeError):
            reader = tail.reader if tail else ActivityReader("", 0)
            snapshot = reader.snapshot(time.time(), "无法读取已绑定会话；显示的是最后记录。")
        content = {k: v for k, v in snapshot.items() if k != "checked_at"}
        if content != last_content or args.once:
            atomic_json(args.state_dir / "activity.json", snapshot)
            last_content = content
        atomic_json(args.state_dir / "activity-heartbeat.json", {
            "checked_at": time.time(), "thread_id": snapshot["thread_id"]})
        if args.once:
            break
        time.sleep(1)


if __name__ == "__main__":
    main()
