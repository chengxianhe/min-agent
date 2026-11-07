"""Opt-in bridge to one existing desktop thread; cannot spawn an executor."""
import argparse
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import threading
import uuid

from min_agent_desktop.store import default_directory
from .card_binding import register_connection
from .current_session import CurrentSession, SessionUnavailable
from .files import private_directory, read_json, save_json
from .local_socket import RpcError, TransportError
from .ilink import LinkError
from .login import login
from .relay_mirror import check_binding
from .relay_service import run_relay


def main():
    parser = argparse.ArgumentParser(description="把本人微信连接到已有 Codex 会话")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--card-dir", type=Path, default=default_directory())
    parser.add_argument("--socket", type=Path, default=Path.home() / ".codex/app-server-control/app-server-control.sock")
    parser.add_argument("--window", type=Path)
    args = parser.parse_args()
    uuid.UUID(args.thread_id)
    os.umask(0o077)
    directory = private_directory(args.state_dir.resolve())
    with (directory / "service.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("微信监听已经在运行；先停止旧监听")
        check_binding(args.card_dir, args.thread_id)
        session = CurrentSession(args.socket, args.thread_id)
        connection = session.open()
        try:
            session.inspect(connection)
        finally:
            connection.close()
        (directory / "stop-request").unlink(missing_ok=True)
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())

        def watch():
            while not stop.wait(.5):
                if (directory / "stop-request").exists():
                    stop.set()

        threading.Thread(target=watch, daemon=True).start()
        register_connection(args.card_dir, directory)
        save_json(directory / "connection.json", {"mode": "current_session", "thread_id": args.thread_id,
                  "status": "loading", "message": "正在准备当前会话的微信连接。"})
        if args.window:
            subprocess.Popen([str(args.window.resolve()), str(directory)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            credential_path = directory / "credentials.json"
            credentials = read_json(credential_path) if credential_path.exists() else login(directory, stop)
            if not stop.is_set():
                run_relay(directory, credentials, args.thread_id, args.socket, args.card_dir, stop)
        except LinkError as error:
            save_json(directory / "connection.json", {"mode": "current_session", "thread_id": args.thread_id,
                      "status": "error", "message": str(error)})
            raise
        finally:
            stop.set()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TransportError, RpcError, SessionUnavailable, LinkError):
        raise SystemExit("当前会话转发未能启动；请确认微信已绑定、小看板会话一致、Codex 桌面会话已打开。")
