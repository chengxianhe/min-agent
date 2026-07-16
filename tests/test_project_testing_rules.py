from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectTestingRulesTest(unittest.TestCase):
    def test_agents_documents_testing_layers_and_browser_acceptance_boundary(self) -> None:
        content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        expected_tokens = [
            "## 测试与验收规则",
            "机制单元测试",
            "Agent 场景测试",
            "浏览器验收",
            "源码结构防退化测试",
            "browser manual smoke: PASS",
            "不能用源码检查替代",
        ]
        for token in expected_tokens:
            self.assertIn(token, content)

    def test_runbook_documents_standard_verification_flow(self) -> None:
        content = (ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")

        expected_tokens = [
            "## 标准验证流程",
            "机制单元测试",
            "Agent 场景测试",
            "浏览器验收",
            "工作区清理",
            "browser manual smoke: PASS",
            "browser manual smoke: NOT RUN",
        ]
        for token in expected_tokens:
            self.assertIn(token, content)

    def test_development_plan_rules_require_testing_acceptance_matrix(self) -> None:
        content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        expected_tokens = [
            "### 开发计划必须包含测试验收矩阵",
            "每份开发计划必须列出",
            "run record 里必须出现什么事件链",
            "哪些工具必须出现，哪些工具不能出现",
            "不能把源码检查写成 `browser manual smoke: PASS`",
            "不合格的测试计划示例",
            "只写“运行测试”",
        ]
        for token in expected_tokens:
            self.assertIn(token, content)

    def test_agents_documents_v1_web_agent_testing_rules(self) -> None:
        content = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        expected_tokens = [
            "## V1.0 边界",
            "## V1.0 Web Agent 规则",
            "Web API 单元测试使用标准库本地 HTTP 客户端",
            "Key 泄漏扫描属于 V1.0 验收",
        ]
        for token in expected_tokens:
            self.assertIn(token, content)

    def test_public_readme_documents_first_run_and_data_boundaries(self) -> None:
        content = (ROOT / "README.md").read_text(encoding="utf-8")

        expected_tokens = [
            "## 快速开始",
            "Python 3.10",
            "--workspace examples/workspace",
            "## Agent 如何运行",
            "## Fake 与 DeepSeek",
            "## 数据与安全边界",
            "runs/*.json",
            "## License",
        ]
        for token in expected_tokens:
            self.assertIn(token, content)

    def test_ci_covers_supported_os_and_python_versions(self) -> None:
        content = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
            encoding="utf-8"
        )

        expected_tokens = [
            "ubuntu-latest",
            "macos-latest",
            'python-version: ["3.10", "3.12"]',
            "python -m unittest discover -s tests",
        ]
        for token in expected_tokens:
            self.assertIn(token, content)


if __name__ == "__main__":
    unittest.main()
