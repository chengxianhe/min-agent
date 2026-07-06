from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class ToolRegistryTest(unittest.TestCase):
    def test_register_and_call_tool(self) -> None:
        from min_agent.tool_registry import ToolRegistry
        from min_agent.types import ToolResult, ToolSpec

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="echo", description="Echo input", args_schema={"text": "string"}),
            lambda args: ToolResult(success=True, content=args["text"]),
        )

        result = registry.call("echo", {"text": "hello"})

        self.assertTrue(result.success)
        self.assertEqual(result.content, "hello")

    def test_unknown_tool_returns_failure(self) -> None:
        from min_agent.tool_registry import ToolRegistry

        registry = ToolRegistry()
        result = registry.call("missing", {})

        self.assertFalse(result.success)
        self.assertIn("unknown tool", result.error or "")

    def test_list_specs_exposes_registered_tools(self) -> None:
        from min_agent.tool_registry import ToolRegistry
        from min_agent.types import ToolResult, ToolSpec

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="read_file", description="Read file", args_schema={"path": "string"}),
            lambda args: ToolResult(success=True, content="ok"),
        )

        specs = registry.list_specs()

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].name, "read_file")

    def test_tool_exception_returns_failure(self) -> None:
        from min_agent.tool_registry import ToolRegistry
        from min_agent.types import ToolSpec

        registry = ToolRegistry()

        def fail(_args: dict) -> object:
            raise RuntimeError("boom")

        registry.register(ToolSpec(name="fail", description="Fail"), fail)

        result = registry.call("fail", {})

        self.assertFalse(result.success)
        self.assertIn("tool fail failed", result.error or "")


    def test_get_spec_returns_spec_for_known_tool(self) -> None:
        from min_agent.tool_registry import ToolRegistry
        from min_agent.types import ToolSpec

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="read_file", description="Read file", requires_permission=False),
            lambda args: None,
        )

        spec = registry.get_spec("read_file")

        self.assertIsNotNone(spec)
        self.assertEqual(spec.name, "read_file")
        self.assertFalse(spec.requires_permission)

    def test_get_spec_returns_none_for_unknown_tool(self) -> None:
        from min_agent.tool_registry import ToolRegistry

        registry = ToolRegistry()
        spec = registry.get_spec("missing")

        self.assertIsNone(spec)

    def test_get_spec_does_not_change_register_list_or_call(self) -> None:
        from min_agent.tool_registry import ToolRegistry
        from min_agent.types import ToolResult, ToolSpec

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="echo", description="Echo", requires_permission=True),
            lambda args: ToolResult(success=True, content=args.get("text", "")),
        )

        spec = registry.get_spec("echo")
        self.assertTrue(spec.requires_permission)

        specs = registry.list_specs()
        self.assertEqual(len(specs), 1)

        result = registry.call("echo", {"text": "hello"})
        self.assertTrue(result.success)
        self.assertEqual(result.content, "hello")

    def test_validate_call_returns_validator_error(self) -> None:
        from min_agent.tool_registry import ToolRegistry
        from min_agent.types import ToolResult, ToolSpec

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="run_command", description="Run command", requires_permission=True),
            lambda args: ToolResult(success=True),
            validator=lambda args: (
                ToolResult(success=False, error="unknown_command_id")
                if args.get("command_id") != "get_current_time"
                else None
            ),
        )

        error = registry.validate_call("run_command", {"command_id": "delete_everything"})
        self.assertIsNotNone(error)
        self.assertEqual(error.error, "unknown_command_id")

        no_error = registry.validate_call("run_command", {"command_id": "get_current_time"})
        self.assertIsNone(no_error)

    def test_validate_call_returns_none_for_tool_without_validator(self) -> None:
        from min_agent.tool_registry import ToolRegistry
        from min_agent.types import ToolResult, ToolSpec

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="read_file", description="Read file"),
            lambda args: ToolResult(success=True),
        )

        result = registry.validate_call("read_file", {"path": "notes.md"})
        self.assertIsNone(result)

    def test_permission_details_returns_resolved_details(self) -> None:
        from min_agent.tool_registry import ToolRegistry
        from min_agent.types import ToolResult, ToolSpec

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="run_command", description="Run command", requires_permission=True),
            lambda args: ToolResult(success=True),
            permission_describer=lambda args: {
                "command_id": "get_current_time",
                "command": '/bin/date "+%Y-%m-%d %H:%M:%S %Z"',
                "risk": "只读",
            },
        )

        details = registry.permission_details("run_command", {"command_id": "get_current_time"})
        self.assertEqual(details["command_id"], "get_current_time")
        self.assertEqual(details["command"], '/bin/date "+%Y-%m-%d %H:%M:%S %Z"')

    def test_permission_details_returns_empty_for_tool_without_describer(self) -> None:
        from min_agent.tool_registry import ToolRegistry
        from min_agent.types import ToolResult, ToolSpec

        registry = ToolRegistry()
        registry.register(
            ToolSpec(name="read_file", description="Read file"),
            lambda args: ToolResult(success=True),
        )

        details = registry.permission_details("read_file", {"path": "notes.md"})
        self.assertEqual(details, {})


if __name__ == "__main__":
    unittest.main()
