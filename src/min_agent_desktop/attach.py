"""Explicitly bind the card to one conversation, starting with its latest turn."""
import argparse
import json
import uuid
from pathlib import Path

from .activity import timestamp
from .store import default_directory
from .watcher import MAX_LINE, atomic_json, validate_source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", type=Path, required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--state-dir", type=Path, default=default_directory())
    args = parser.parse_args()
    uuid.UUID(args.thread_id)
    source = args.transcript.resolve(strict=True)
    validate_source(source, args.thread_id)
    since = 0
    with source.open("rb") as stream:
        for line in stream:
            if len(line) > MAX_LINE:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if record.get("type") == "event_msg" and record.get("payload", {}).get("type") == "task_started":
                since = timestamp(record.get("timestamp"))
    if since <= 0:
        raise SystemExit("未找到会话轮次，不读取旧聊天")
    atomic_json(args.state_dir / "activity-source.json", {"thread_id": args.thread_id, "path": str(source), "since": since})
    print(json.dumps({"attached_thread": args.thread_id, "since": since}))


if __name__ == "__main__":
    main()
