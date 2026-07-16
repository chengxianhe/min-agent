from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class RuntimeFactoryTest(unittest.TestCase):
    def test_registry_preserves_tool_permissions_and_unknown_command_validation(self) -> None:
        from min_agent.runtime_factory import build_tool_registry

        registry = build_tool_registry(Path("examples/workspace"))
        self.assertFalse(registry.get_spec("read_file").requires_permission)
        self.assertFalse(registry.get_spec("list_dir").requires_permission)
        self.assertTrue(registry.get_spec("write_file").requires_permission)
        self.assertTrue(registry.get_spec("run_command").requires_permission)
        self.assertFalse(registry.validate_call("run_command", {"command_id": "unknown"}).success)

    def test_fake_web_model_never_requires_a_key(self) -> None:
        from min_agent.fake_llm import FakeLLM
        from min_agent.runtime_factory import build_web_decision_model

        model, error = build_web_decision_model(
            "fake",
            api_key=None,
            deepseek_model="deepseek-v4-flash",
            deepseek_base_url="https://api.deepseek.com",
            model_timeout_seconds=30.0,
            model_max_tokens=1200,
        )
        self.assertIsInstance(model, FakeLLM)
        self.assertIsNone(error)

    def test_deepseek_web_model_requires_explicit_key(self) -> None:
        from min_agent.runtime_factory import build_web_decision_model

        model, error = build_web_decision_model(
            "deepseek",
            api_key=None,
            deepseek_model="deepseek-v4-flash",
            deepseek_base_url="https://api.deepseek.com",
            model_timeout_seconds=30.0,
            model_max_tokens=1200,
        )
        self.assertIsNone(model)
        self.assertEqual(error, "DeepSeek Key is not configured for this Web service")
