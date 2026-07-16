from __future__ import annotations

import argparse
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from min_agent.permission_broker import PermissionBroker
from min_agent.run_history import RunHistory
from min_agent.run_manager import RunManager
from min_agent.session_key_store import SessionKeyStore
from min_agent.tools.workspace import ensure_workspace
from min_agent.web_server import WebAgentServer


@dataclass(frozen=True)
class WebAppConfig:
    workspace: Path
    runs_dir: Path
    port: int
    open_browser: bool
    step_delay_seconds: float
    deepseek_model: str
    deepseek_base_url: str
    model_timeout_seconds: float
    model_max_tokens: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="min-agent-web",
        description="Start the local Min Agent Web service.",
    )
    parser.add_argument("--workspace", default="examples/workspace")
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--step-delay", type=float, default=0.4)
    parser.add_argument("--deepseek-model", default="deepseek-v4-flash")
    parser.add_argument("--deepseek-base-url", default="https://api.deepseek.com")
    parser.add_argument("--model-timeout", type=float, default=30.0)
    parser.add_argument("--model-max-tokens", type=int, default=1200)
    return parser


def parse_config(argv: Sequence[str] | None = None) -> WebAppConfig:
    args = build_parser().parse_args(argv)
    if not 0 <= args.port <= 65535:
        raise ValueError("port must be 0..65535")

    workspace = ensure_workspace(args.workspace)
    return WebAppConfig(
        workspace=workspace,
        runs_dir=Path(args.runs_dir).resolve(),
        port=args.port,
        open_browser=not args.no_browser,
        step_delay_seconds=args.step_delay,
        deepseek_model=args.deepseek_model,
        deepseek_base_url=args.deepseek_base_url,
        model_timeout_seconds=args.model_timeout,
        model_max_tokens=args.model_max_tokens,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        config = parse_config(argv)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"Error: {exc}")
        return 2

    key_store = SessionKeyStore()
    permission_broker = PermissionBroker()
    manager = RunManager(
        config.workspace,
        config.runs_dir,
        key_store,
        permission_broker,
        step_delay_seconds=config.step_delay_seconds,
        deepseek_model=config.deepseek_model,
        deepseek_base_url=config.deepseek_base_url,
        model_timeout_seconds=config.model_timeout_seconds,
        model_max_tokens=config.model_max_tokens,
    )
    server: WebAgentServer | None = None

    try:
        server = WebAgentServer(
            manager,
            RunHistory(config.runs_dir),
            key_store,
            Path(__file__).resolve().parents[2] / "web",
            config.port,
        )
        server.start()
        print(f"Workspace: {config.workspace}", flush=True)
        print(f"Web Agent: {server.url}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)

        if config.open_browser and not webbrowser.open(server.url):
            print(f"Open this URL manually: {server.url}")

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0
    except OSError as exc:
        print(f"Error: {exc}")
        return 2
    finally:
        manager.close()
        if server is not None:
            server.close()
        key_store.clear()


if __name__ == "__main__":
    raise SystemExit(main())
