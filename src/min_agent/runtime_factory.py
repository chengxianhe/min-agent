from __future__ import annotations

from pathlib import Path

from min_agent.command_registry import build_default_command_registry
from min_agent.decision_model import DecisionModel
from min_agent.deepseek_client import DeepSeekClient
from min_agent.deepseek_llm import DeepSeekLLM
from min_agent.fake_llm import FakeLLM
from min_agent.tool_registry import ToolRegistry
from min_agent.tools.command import run_command
from min_agent.tools.workspace import list_dir, read_file, write_file
from min_agent.types import ToolSpec


def build_tool_registry(workspace: Path) -> ToolRegistry:
    command_registry = build_default_command_registry()
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "read_file",
            "Read a UTF-8 text file inside the configured workspace.",
            {"path": "string"},
            False,
        ),
        lambda args: read_file(workspace, args),
    )
    registry.register(
        ToolSpec(
            "list_dir",
            "List files and directories inside the configured workspace.",
            {"path": "string"},
            False,
        ),
        lambda args: list_dir(workspace, args),
    )
    registry.register(
        ToolSpec(
            "write_file",
            "Create a new UTF-8 text file inside the configured workspace after approval.",
            {"path": "string", "content": "string", "mode": "string"},
            True,
        ),
        lambda args: write_file(workspace, args),
    )
    registry.register(
        ToolSpec(
            "run_command",
            "Run one predefined local command action after approval.",
            {"command_id": "string"},
            True,
        ),
        lambda args: run_command(workspace, args, command_registry),
        validator=command_registry.validate_args,
        permission_describer=lambda args: command_registry.permission_details(
            args,
            workspace,
        ),
    )
    return registry


def build_web_decision_model(
    decision_model: str,
    *,
    api_key: str | None,
    deepseek_model: str,
    deepseek_base_url: str,
    model_timeout_seconds: float,
    model_max_tokens: int,
) -> tuple[DecisionModel | None, str | None]:
    if decision_model == "fake":
        return FakeLLM(), None
    if decision_model != "deepseek":
        return None, f"Unknown decision model: {decision_model}"
    if not api_key:
        return None, "DeepSeek Key is not configured for this Web service"
    client = DeepSeekClient(
        api_key=api_key,
        model=deepseek_model,
        base_url=deepseek_base_url,
        timeout_seconds=model_timeout_seconds,
        max_tokens=model_max_tokens,
    )
    return DeepSeekLLM(client=client, model=deepseek_model), None
