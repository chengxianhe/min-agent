from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WebAgentSourceTest(unittest.TestCase):
    def test_history_replay_is_not_overwritten_by_current_run_routing(self) -> None:
        source = (ROOT / "web" / "web_agent.js").read_text(encoding="utf-8")

        self.assertIn("viewingHistoricalRunId", source)
        self.assertIn("if (name === \"trace\" && runId)", source)
        self.assertIn("await loadHistoricalRun(runId)", source)
        self.assertIn("state.viewingHistoricalRunId = null", source)

    def test_live_events_do_not_mutate_historical_replay(self) -> None:
        source = (ROOT / "web" / "web_agent.js").read_text(encoding="utf-8")

        self.assertIn('if (!state.viewingHistoricalRunId && state.activeRoute === "trace") viewer.applyEvent(event)', source)
        self.assertIn("function updateCurrentRun(event)", source)

    def test_unknown_historical_model_is_not_mislabeled_as_fake(self) -> None:
        source = (ROOT / "web" / "web_agent.js").read_text(encoding="utf-8")

        self.assertIn('if (model === "deepseek") return "DeepSeek";', source)
        self.assertIn('if (model === "fake") return "Fake";', source)
        self.assertIn('return "Unknown";', source)
        self.assertNotIn('model === "deepseek" ? "DeepSeek" : "Fake"', source)

    def test_web_shell_has_required_routes_and_safe_live_state_contract(self) -> None:
        html = (ROOT / "web" / "web_agent.html").read_text(encoding="utf-8")
        source = (ROOT / "web" / "web_agent.js").read_text(encoding="utf-8")

        for token in (
            'data-route="new"', 'data-route="trace"', 'data-route="history"',
            'id="pending-permission-button"', 'id="workspace-value"',
            'id="model-fake"', 'id="model-deepseek"', 'id="key-panel"',
            'id="history-list"', 'id="history-detail"', 'id="permission-drawer"',
        ):
            self.assertIn(token, html)
        self.assertIn("function parseRoute", source)
        self.assertIn("function refreshPendingPermission", source)
        self.assertIn("[50, 100, 200, 400, 800]", source)
        self.assertIn("new EventSource(`/api/runs/current/events?run_id=${encodeURIComponent(run.run_id)}`)", source)
        self.assertIn("viewer.loadRun({ runId: run.run_id, status: run.status, events: run.events || [] })", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)

    def test_launch_page_offers_three_prefill_only_demo_prompts(self) -> None:
        html = (ROOT / "web" / "web_agent.html").read_text(encoding="utf-8")
        source = (ROOT / "web" / "web_agent.js").read_text(encoding="utf-8")

        self.assertEqual(html.count("data-preset-goal="), 3)
        self.assertIn("dataset.presetGoal", source)
        self.assertIn('$("goal-input").focus()', source)
        self.assertNotIn("presetButton.click", source)

    def test_web_viewer_uses_runtime_label_without_internal_boundary_note(self) -> None:
        html = (ROOT / "web" / "web_agent.html").read_text(encoding="utf-8")
        core = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertNotIn("viewer-boundary-note", html)
        self.assertNotIn("V1.0 只在 Viewer 外增加", html)
        self.assertIn("Runtime · ${event.phase} · ${event.status}", core)
        self.assertNotIn("CLI · ${event.phase} · ${event.status}", core)

    def test_web_shell_preserves_frozen_prototype_information_architecture(self) -> None:
        html = (ROOT / "web" / "web_agent.html").read_text(encoding="utf-8")
        css = (ROOT / "web" / "web_agent.css").read_text(encoding="utf-8")

        for token in (
            'class="app-header"', 'class="launch-layout"', 'class="card launch-card"',
            'class="side-stack"', 'class="viewer-shell"',
            'class="history-layout"', 'class="card history-detail"', 'class="permission-drawer"',
            'id="request-run-context"', 'id="request-model"', 'id="request-workspace"',
        ):
            self.assertIn(token, html)
        self.assertNotIn('class="run-meta-bar"', html)
        self.assertNotIn("prototype-bar", html)
        self.assertNotIn("data-demo", html)
        self.assertIn(".launch-layout", css)
        self.assertIn(".history-layout", css)
        self.assertIn(".permission-drawer", css)
        self.assertIn("@media(max-width:760px)", css)

    def test_trace_page_uses_readable_type_and_a_wide_viewer_canvas(self) -> None:
        css = (ROOT / "web" / "web_agent.css").read_text(encoding="utf-8")

        self.assertIn('"PingFang SC"', css)
        self.assertIn("width:min(1680px,calc(100% - 64px))", css)
        self.assertIn(".viewer-shell .shell{max-width:none;margin:0;padding:0}", css)
        self.assertIn("grid-template-columns:minmax(360px,.58fr) minmax(0,1.42fr)", css)

    def test_web_trace_context_is_inline_and_task_steps_are_compact_rows(self) -> None:
        css = (ROOT / "web" / "web_agent.css").read_text(encoding="utf-8")

        self.assertIn(".request-run-context", css)
        self.assertIn(".viewer-shell .task-list { grid-template-columns:repeat(auto-fit,minmax(190px,1fr));", css)
        self.assertIn(".viewer-shell .task-card { min-height:0;", css)
