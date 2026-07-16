from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class WebAppTest(unittest.TestCase):
    def test_parser_has_web_service_options_without_goal_or_model_selection(self) -> None:
        from min_agent.web_app import build_parser

        parser = build_parser()
        args = parser.parse_args(["--port", "0", "--no-browser"])
        self.assertEqual(args.workspace, "examples/workspace")
        self.assertEqual(args.port, 0)
        self.assertFalse(hasattr(args, "goal"))
        self.assertFalse(hasattr(args, "decision_model"))

    def test_parse_config_preserves_model_runtime_options(self) -> None:
        from min_agent.web_app import parse_config

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()

            config = parse_config(
                [
                    "--workspace",
                    str(workspace),
                    "--runs-dir",
                    str(root / "records"),
                    "--port",
                    "0",
                    "--no-browser",
                    "--step-delay",
                    "0.1",
                    "--deepseek-model",
                    "custom-model",
                    "--deepseek-base-url",
                    "https://example.test/v1",
                    "--model-timeout",
                    "7.5",
                    "--model-max-tokens",
                    "321",
                ]
            )

        self.assertEqual(config.workspace, workspace.resolve())
        self.assertEqual(config.runs_dir, (root / "records").resolve())
        self.assertEqual(config.port, 0)
        self.assertFalse(config.open_browser)
        self.assertEqual(config.step_delay_seconds, 0.1)
        self.assertEqual(config.deepseek_model, "custom-model")
        self.assertEqual(config.deepseek_base_url, "https://example.test/v1")
        self.assertEqual(config.model_timeout_seconds, 7.5)
        self.assertEqual(config.model_max_tokens, 321)
