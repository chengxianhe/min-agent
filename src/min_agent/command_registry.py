"""Immutable command registry for predefined command actions.

Every command is defined as a fixed recipe. Models can only reference
command_id values; they cannot provide raw commands, custom arguments,
shell operators, or runtime parameters.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from min_agent.types import ToolResult


@dataclass(frozen=True)
class CommandDefinition:
    """An immutable recipe for one predefined command action."""

    command_id: str
    description: str
    argv: tuple[str, ...]
    display_command: str
    risk: str
    timeout_seconds: float = 5.0
    output_limit: int = 4096


class CommandRegistry:
    """Holds registered CommandDefinitions and validates incoming args."""

    def __init__(self) -> None:
        self._definitions: dict[str, CommandDefinition] = {}

    def register(self, definition: CommandDefinition) -> None:
        if definition.command_id in self._definitions:
            raise ValueError(f"command already registered: {definition.command_id}")
        self._definitions[definition.command_id] = definition

    def get(self, command_id: str) -> CommandDefinition | None:
        return self._definitions.get(command_id)

    def validate_args(self, args: dict[str, Any]) -> ToolResult | None:
        """Return a ToolResult error if args are invalid, or None if valid."""
        if set(args) != {"command_id"} or not isinstance(args.get("command_id"), str):
            return ToolResult(success=False, error="invalid_command_args")
        if self.get(args["command_id"]) is None:
            return ToolResult(success=False, error="unknown_command_id")
        return None

    def permission_details(self, args: dict[str, Any], workspace: Path) -> dict[str, Any]:
        definition = self._definitions[args["command_id"]]
        return {
            "command_id": definition.command_id,
            "command": definition.display_command,
            "workspace": str(workspace),
            "risk": definition.risk,
        }


def build_default_command_registry() -> CommandRegistry:
    """Create a registry populated with the V0.7 default command."""
    registry = CommandRegistry()
    registry.register(
        CommandDefinition(
            command_id="get_current_time",
            description="Get the current local system time.",
            argv=("/bin/date", "+%Y-%m-%d %H:%M:%S %Z"),
            display_command='/bin/date "+%Y-%m-%d %H:%M:%S %Z"',
            risk="该命令只读取本机当前时间，不修改文件、不访问网络。",
        )
    )
    return registry
