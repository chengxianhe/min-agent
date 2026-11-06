"""Agent-facing tool: python -m min_agent_desktop begin/update/read."""

import argparse
import json
from pathlib import Path

from .store import ProgressStore


def main() -> int:
    parser = argparse.ArgumentParser(description="更新桌面任务卡片；只写进度摘要，不执行任务")
    parser.add_argument("--state-dir", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    begin = commands.add_parser("begin")
    begin.add_argument("--title", required=True)
    begin.add_argument("--action", required=True)
    begin.add_argument("--replace", action="store_true")
    update = commands.add_parser("update")
    update.add_argument("--task-id", required=True)
    update.add_argument("--status", required=True)
    update.add_argument("--action", required=True)
    update.add_argument("--detail", default="")
    commands.add_parser("read")
    args = parser.parse_args()
    store = ProgressStore(args.state_dir)
    try:
        if args.command == "begin":
            state = store.begin(args.title, args.action, args.replace)
        elif args.command == "update":
            state = store.update(args.task_id, args.status, args.action, args.detail)
        else:
            state = store.read()
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"无法更新卡片：{error}\n")
    print(json.dumps(state, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
