"""Tests for command_registry module."""

import unittest

from min_agent.command_registry import build_default_command_registry


class CommandRegistryTest(unittest.TestCase):
    def test_get_current_time_has_fixed_recipe(self) -> None:
        registry = build_default_command_registry()
        definition = registry.get("get_current_time")
        self.assertIsNotNone(definition)
        self.assertEqual(definition.argv, ("/bin/date", "+%Y-%m-%d %H:%M:%S %Z"))
        self.assertEqual(definition.timeout_seconds, 5.0)
        self.assertEqual(definition.output_limit, 4096)

    def test_validate_args_accepts_only_command_id(self) -> None:
        registry = build_default_command_registry()
        self.assertIsNone(registry.validate_args({"command_id": "get_current_time"}))
        result = registry.validate_args({"command_id": "get_current_time", "command": "date"})
        self.assertEqual(result.error, "invalid_command_args")

    def test_unknown_command_id_is_rejected(self) -> None:
        registry = build_default_command_registry()
        result = registry.validate_args({"command_id": "delete_everything"})
        self.assertEqual(result.error, "unknown_command_id")

    def test_missing_command_id_is_rejected(self) -> None:
        registry = build_default_command_registry()
        result = registry.validate_args({})
        self.assertEqual(result.error, "invalid_command_args")

    def test_non_string_command_id_is_rejected(self) -> None:
        registry = build_default_command_registry()
        result = registry.validate_args({"command_id": 123})
        self.assertEqual(result.error, "invalid_command_args")

    def test_display_command_matches_prototype(self) -> None:
        registry = build_default_command_registry()
        definition = registry.get("get_current_time")
        self.assertEqual(
            definition.display_command,
            '/bin/date "+%Y-%m-%d %H:%M:%S %Z"',
        )

    def test_risk_field_is_present(self) -> None:
        registry = build_default_command_registry()
        definition = registry.get("get_current_time")
        self.assertIn("只读取", definition.risk)
        self.assertIn("不修改", definition.risk)
        self.assertIn("不访问网络", definition.risk)
