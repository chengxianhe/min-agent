"""No-shell command execution tool.

Executes predefined command actions using fixed argument arrays.
Never passes arguments through a shell, and never accepts raw
command strings or custom parameters from the model.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from min_agent.command_registry import CommandRegistry
from min_agent.types import ToolResult


def run_command(
    workspace: Path,
    args: dict[str, Any],
    registry: CommandRegistry,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> ToolResult:
    """Execute a predefined command action without a shell.

    Args:
        workspace: Fixed working directory for the command.
        args: Must contain exactly {"command_id": "<registered_id>"}.
        registry: Source of immutable command definitions.
        runner: Optional injection point for tests. Defaults to subprocess.run.

    Returns:
        ToolResult with structured metadata regardless of success or failure.
    """
    # Validate args through the registry before any execution.
    validation_error = registry.validate_args(args)
    if validation_error is not None:
        return validation_error

    command_id = args["command_id"]
    definition = registry.get(command_id)
    assert definition is not None  # validated above

    process_runner = runner or subprocess.run
    started_at = time.monotonic()

    try:
        completed = process_runner(
            list(definition.argv),
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=definition.timeout_seconds,
            shell=False,
            check=False,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - started_at) * 1000)
        return ToolResult(
            success=False,
            error="command_timeout",
            metadata={
                "command_id": command_id,
                "display_command": definition.display_command,
                "workspace": str(workspace),
                "exit_code": None,
                "duration_ms": duration_ms,
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "timed_out": True,
            },
        )
    except (FileNotFoundError, OSError):
        duration_ms = int((time.monotonic() - started_at) * 1000)
        return ToolResult(
            success=False,
            error="command_start_failed",
            metadata={
                "command_id": command_id,
                "display_command": definition.display_command,
                "workspace": str(workspace),
                "exit_code": None,
                "duration_ms": duration_ms,
                "stdout": "",
                "stderr": "",
                "stdout_truncated": False,
                "stderr_truncated": False,
                "timed_out": False,
            },
        )

    duration_ms = int((time.monotonic() - started_at) * 1000)

    stdout_raw = completed.stdout or ""
    stderr_raw = completed.stderr or ""

    stdout_truncated = len(stdout_raw) > definition.output_limit
    stderr_truncated = len(stderr_raw) > definition.output_limit

    stdout_safe = stdout_raw[: definition.output_limit]
    stderr_safe = stderr_raw[: definition.output_limit]

    success = completed.returncode == 0

    if success:
        content = stdout_safe.strip()
    else:
        content = (
            f"Command failed with exit_code={completed.returncode}. "
            f"stderr: {stderr_safe[:200]}"
        )

    return ToolResult(
        success=success,
        content=content,
        error=None if success else f"exit_code={completed.returncode}",
        metadata={
            "command_id": command_id,
            "display_command": definition.display_command,
            "workspace": str(workspace),
            "exit_code": completed.returncode,
            "duration_ms": duration_ms,
            "stdout": stdout_safe,
            "stderr": stderr_safe,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
            "timed_out": False,
        },
    )
