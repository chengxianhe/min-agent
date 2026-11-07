"""python -m min_agent_wechat --workspace DIR --state-dir DIR [--window BINARY]."""
import argparse
import fcntl
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading

from .files import private_directory, read_json, save_json
from .card_binding import register_connection
from .ilink import LinkError
from .login import login
from .service import serve


def main():
    parser = argparse.ArgumentParser(description="个人微信文字任务桥接，首次运行需本人扫码")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--card-dir", type=Path)
    parser.add_argument("--codex", default=shutil.which("codex"))
    parser.add_argument("--window", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    if not workspace.is_dir() or workspace == Path("/") or not args.codex:
        parser.error("需要有效的固定工作目录和本机 Codex CLI")
    directory = private_directory(args.state_dir.resolve())
    os.umask(0o077)
    fd = os.open(directory / "service.lock", os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("该连接服务已经在运行")
        config = directory / "config.json"
        if config.exists() and read_json(config).get("workspace") != str(workspace):
            parser.error("工作目录与已有绑定不一致，请使用新的状态目录")
        save_json(config, {"workspace": str(workspace)})
        (directory / "stop-request").unlink(missing_ok=True)
        (directory / "verify-code.json").unlink(missing_ok=True)
        stop = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        signal.signal(signal.SIGINT, lambda *_: stop.set())

        def watch_stop():
            while not stop.wait(0.5):
                if (directory / "stop-request").exists():
                    stop.set()

        threading.Thread(target=watch_stop, daemon=True).start()
        try:
            register_connection(args.card_dir, directory)
            save_json(directory / "connection.json", {"status": "loading", "message": "正在准备连接…"})
            if args.window:
                subprocess.Popen([str(args.window.resolve()), str(directory)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            credential_path = directory / "credentials.json"
            credentials = read_json(credential_path) if credential_path.exists() else login(directory, stop)
            if not stop.is_set():
                serve(directory, credentials, workspace, args.codex, args.card_dir, stop)
        except (OSError, ValueError, LinkError) as error:
            # Only our fixed iLink diagnostics are safe for UI/logs.
            message = str(error) if isinstance(error, LinkError) else "本机配置或运行错误；请检查安装和目录权限。"
            save_json(directory / "connection.json", {"status": "error", "message": message})
            print(message, flush=True)
            return 1
        finally:
            stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
