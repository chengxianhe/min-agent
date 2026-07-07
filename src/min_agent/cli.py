from __future__ import annotations

import argparse
import os
import time
import webbrowser
from pathlib import Path
from typing import Any, Sequence

from min_agent.agent_loop import AgentLoop
from min_agent.command_registry import build_default_command_registry
from min_agent.context_builder import ContextBuilder
from min_agent.context_loader import ContextLoader
from min_agent.decision_model import DecisionModel
from min_agent.deepseek_client import DeepSeekClient
from min_agent.deepseek_llm import DeepSeekLLM
from min_agent.fake_llm import FakeLLM
from min_agent.tool_registry import ToolRegistry
from min_agent.tools.command import run_command
from min_agent.tools.workspace import ensure_workspace, list_dir, read_file, write_file
from min_agent.trace_recorder import TraceRecorder
from min_agent.trace_server import TraceServer
from min_agent.types import AgentAction, ToolSpec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="min-agent",
        description="Start the minimal observable agent demo.",
    )
    parser.add_argument("goal", help="User goal for the demo agent.")
    parser.add_argument("--workspace", default="examples/workspace", help="Workspace directory.")
    parser.add_argument("--runs-dir", default="runs", help="Directory for run records.")
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Preferred trace viewer port. Use 0 to let the OS choose a free port.",
    )
    parser.add_argument("--no-browser", action="store_true", help="Print viewer URL without opening a browser.")
    parser.add_argument("--no-viewer", action="store_true", help="Run without starting the trace server.")
    parser.add_argument("--keep-open-seconds", type=float, default=5, help="Keep viewer server alive after completion.")
    parser.add_argument("--step-delay", type=float, default=0.4, help="Delay between visible steps.")
    parser.add_argument(
        "--decision-model",
        choices=["fake", "deepseek"],
        default="fake",
        help="Decision model backend.",
    )
    parser.add_argument("--deepseek-model", default="deepseek-v4-flash", help="DeepSeek model name.")
    parser.add_argument(
        "--deepseek-base-url",
        default="https://api.deepseek.com",
        help="DeepSeek OpenAI-compatible base URL.",
    )
    parser.add_argument("--model-max-tokens", type=int, default=1200, help="Maximum model output tokens.")
    return parser


def build_decision_model(args: argparse.Namespace) -> tuple[DecisionModel | None, str | None]:
    if args.decision_model == "fake":
        return FakeLLM(), None

    if args.decision_model == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            return None, "DEEPSEEK_API_KEY is required when --decision-model deepseek"

        client = DeepSeekClient(
            api_key=api_key,
            model=args.deepseek_model,
            base_url=args.deepseek_base_url,
            max_tokens=args.model_max_tokens,
        )
        return DeepSeekLLM(client=client, model=args.deepseek_model), None

    return None, f"Unknown decision model: {args.decision_model}"


def build_tool_registry(workspace: Path) -> ToolRegistry:
    command_registry = build_default_command_registry()
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="read_file",
            description="Read a UTF-8 text file inside the configured workspace.",
            args_schema={"path": "string"},
            requires_permission=False,
        ),
        lambda tool_args: read_file(workspace, tool_args),
    )
    registry.register(
        ToolSpec(
            name="list_dir",
            description="List files and directories inside the configured workspace.",
            args_schema={"path": "string"},
            requires_permission=False,
        ),
        lambda tool_args: list_dir(workspace, tool_args),
    )
    registry.register(
        ToolSpec(
            name="write_file",
            description="Create a new UTF-8 text file inside the configured workspace after approval.",
            args_schema={"path": "string", "content": "string", "mode": "string"},
            requires_permission=True,
        ),
        lambda tool_args: write_file(workspace, tool_args),
    )
    registry.register(
        ToolSpec(
            name="run_command",
            description="Run one predefined local command action after approval.",
            args_schema={"command_id": "string"},
            requires_permission=True,
        ),
        lambda tool_args: run_command(workspace, tool_args, command_registry),
        validator=command_registry.validate_args,
        permission_describer=lambda tool_args: command_registry.permission_details(tool_args, workspace),
    )
    return registry


def preview_text(value: str, limit: int = 200) -> str:
    return value if len(value) <= limit else value[:limit] + "..."


def confirm_tool_call(action: AgentAction, details: dict[str, Any]) -> bool:
    print()
    print(f"Permission required: {action.tool_name}")
    if action.tool_name == "run_command" and details:
        print(f"Action: {details.get('command_id', 'unknown')}")
        print(f"Command: {details.get('command', 'unknown')}")
        print(f"Workspace: {details.get('workspace', 'unknown')}")
        print(f"Risk: {details.get('risk', 'unknown')}")
    elif "path" in action.args:
        print(f"Path: {action.args['path']}")
    print(f"Reason: {action.reason}")
    content = action.args.get("content")
    if isinstance(content, str) and content:
        print("Preview:")
        print(preview_text(content))
    print()
    answer = input("Approve? [y/N] ")
    return answer.strip().lower() == "y"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        workspace = ensure_workspace(args.workspace)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"Error: {exc}")
        return 2

    llm, model_error = build_decision_model(args)
    if model_error is not None:
        print(f"Error: {model_error}")
        return 2

    recorder = TraceRecorder(user_goal=args.goal, workspace=str(workspace))
    server: TraceServer | None = None

    try:
        if not args.no_viewer:
            try:
                server = TraceServer(
                    recorder=recorder,
                    web_dir=Path(__file__).resolve().parents[2] / "web",
                    preferred_port=args.port,
                )
                server.start()
            except OSError as exc:
                if server is not None:
                    server.close()
                print(f"Error: could not start trace viewer: {exc}")
                return 2
            print(f"Trace viewer: {server.url}")
            if not args.no_browser:
                opened = webbrowser.open(server.url)
                if not opened:
                    print(f"Open this URL manually: {server.url}")
        else:
            print("Trace viewer disabled.")

        registry = build_tool_registry(workspace)

        context_loader = ContextLoader(
            workspace=str(workspace),
            runs_dir=args.runs_dir,
            decision_model=args.decision_model,
        )
        loop = AgentLoop(
            context_builder=ContextBuilder(context_loader=context_loader),
            llm=llm,
            tools=registry,
            recorder=recorder,
            workspace=str(workspace),
            step_delay_seconds=args.step_delay,
            permission_callback=lambda action, details: confirm_tool_call(action, details),
        )
        result = loop.run(args.goal)
        record_path = recorder.save(args.runs_dir, status="completed" if result.success else "failed")

        print(result.message)
        print(f"Run record: {record_path}")

        if server is not None and args.keep_open_seconds > 0:
            try:
                time.sleep(args.keep_open_seconds)
            except KeyboardInterrupt:
                pass
        return 0
    except KeyboardInterrupt:
        recorder.emit(
            phase="run_interrupted",
            status="interrupted",
            title="任务已中断",
            reason="用户通过 Ctrl+C 中断",
        )
        record_path = recorder.save(args.runs_dir, status="interrupted")
        print(f"Interrupted. Run record: {record_path}")
        return 130
    finally:
        if server is not None:
            server.close()


if __name__ == "__main__":
    raise SystemExit(main())
