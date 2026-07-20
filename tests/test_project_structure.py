from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))


class ProjectStructureTest(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        required_paths = [
            "AGENTS.md",
            ".gitignore",
            ".github/workflows/tests.yml",
            "CHANGELOG.md",
            "LICENSE",
            "README.md",
            "pyproject.toml",
            "src/min_agent/__init__.py",
            "src/min_agent/agent_loop.py",
            "src/min_agent/cli.py",
            "src/min_agent/context_builder.py",
            "src/min_agent/decision_model.py",
            "src/min_agent/deepseek_client.py",
            "src/min_agent/deepseek_llm.py",
            "src/min_agent/fake_llm.py",
            "src/min_agent/tool_registry.py",
            "src/min_agent/trace_recorder.py",
            "src/min_agent/trace_server.py",
            "src/min_agent/types.py",
            "src/min_agent/tools/__init__.py",
            "src/min_agent/tools/workspace.py",
            "examples/workspace/notes.md",
            "examples/workspace/project.md",
            "examples/workspace/architecture.md",
            "examples/workspace/usage.md",
            "web/trace_viewer.html",
            "web/trace_viewer.css",
            "web/trace_viewer.js",
            "runs/.gitkeep",
            "docs/assets/v1.0/web-agent-overview.png",
            "docs/architecture.md",
            "docs/runbook.md",
        ]

        for relative_path in required_paths:
            with self.subTest(relative_path=relative_path):
                self.assertTrue((ROOT / relative_path).exists())

    def test_project_rules_keep_agent_loop_extensible(self) -> None:
        rules = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("AgentLoop", rules)
        self.assertIn("FakeLLM", rules)
        self.assertIn("ToolRegistry", rules)
        self.assertIn("不能写死固定 7 步流程", rules)

    def test_active_project_identity_uses_min_agent_name(self) -> None:
        legacy_name = "min-agent-" + "demo"
        active_identity_files = [
            ".codex-claude-collaboration.json",
            "AGENTS.md",
            "CHANGELOG.md",
            "README.md",
            "docs/architecture.md",
            "docs/runbook.md",
            "docs/superpowers/v1.1/acceptance.md",
            "docs/superpowers/v1.1/implementation-plan.md",
            "docs/superpowers/v1.1/product-design.md",
            "docs/superpowers/v1.1/ui-audit.md",
            "docs/superpowers/v1.1/web-agent-prototype.html",
            "examples/workspace/project.md",
            "pyproject.toml",
            "src/min_agent/deepseek_llm.py",
            "src/min_agent/tools/__init__.py",
            "tests/test_cli_scenarios.py",
            "tests/test_fake_llm.py",
        ]

        for relative_path in active_identity_files:
            with self.subTest(relative_path=relative_path):
                content = (ROOT / relative_path).read_text(encoding="utf-8")
                self.assertNotIn(legacy_name, content)

        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('name = "min-agent"', pyproject)
        self.assertIn("https://github.com/JinweiX/min-agent", pyproject)
        self.assertIn("# Min Agent", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn(
            '"project_id": "min-agent"',
            (ROOT / ".codex-claude-collaboration.json").read_text(encoding="utf-8"),
        )

    def test_cli_runs_with_example_workspace_without_viewer(self) -> None:
        import tempfile

        from min_agent.cli import main

        with tempfile.TemporaryDirectory() as tmp:
            result = main(
                [
                    "请读取 notes.md 并总结",
                    "--workspace",
                    "examples/workspace",
                    "--runs-dir",
                    tmp,
                    "--no-viewer",
                    "--no-browser",
                    "--step-delay",
                    "0",
                ]
            )

        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
