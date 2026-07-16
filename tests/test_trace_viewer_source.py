from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TraceViewerSourceTest(unittest.TestCase):
    def test_eventsource_error_does_not_override_terminal_status(self) -> None:
        core = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        wrapper = (ROOT / "web" / "trace_viewer.js").read_text(encoding="utf-8")

        self.assertIn("function isTerminalStatus", core)
        self.assertIn('!["completed", "failed", "interrupted"].includes(status)', wrapper)

    def test_step_detail_renders_model_call_sections(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("function renderModelDecisionStep", source)
        self.assertIn("大模型返回 message.content", source)
        self.assertIn("未调用大模型", source)
        self.assertIn("原始事件", source)

    def test_timeline_renders_agent_module_badges(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("function moduleForPhase", source)
        self.assertIn("agent-module-badge", source)
        self.assertIn('"context_built": "Context"', source)
        self.assertIn('"llm_decision": "Model / Reasoning"', source)
        self.assertIn('"tool_started": "Tools"', source)
        self.assertIn('"observation_added": "Memory / State"', source)
        self.assertIn('"final_answer": "Agent Loop"', source)

    def test_viewer_contains_v4_layout_containers(self) -> None:
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")

        self.assertIn('id="run-summary"', html)
        self.assertIn('id="original-request"', html)
        self.assertIn('id="final-answer"', html)
        self.assertIn('id="round-list"', html)
        self.assertIn('id="round-detail"', html)
        self.assertLess(html.index('id="original-request"'), html.index('id="final-answer"'))
        self.assertLess(html.index('id="final-answer"'), html.index('id="round-list"'))

    def test_viewer_groups_events_by_agentic_loop_rounds(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("selectedRoundId", source)
        self.assertIn("function buildRounds", source)
        self.assertIn("function buildRunSummary", source)
        self.assertIn("function renderRunSummary", source)
        self.assertIn("function renderOriginalRequest", source)
        self.assertIn("function renderRoundList", source)
        self.assertIn("function renderRoundDetail", source)
        self.assertIn("function renderEventStep", source)
        self.assertIn("context_built", source)
        self.assertIn("llm_decision", source)

    def test_model_decision_details_remain_explainable(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("function renderModelDecisionStep", source)
        self.assertIn("System Prompt", source)
        self.assertIn("User Prompt", source)
        self.assertIn("message.content", source)
        self.assertIn("未调用大模型", source)
        self.assertIn("解析后的决策", source)
        self.assertIn("原始事件", source)

    def test_v0_4_does_not_add_agent_controls_or_external_assets(self) -> None:
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        forbidden_html = [
            "https://",
            "http://",
            "cdn.",
            "bootstrap",
            "tailwind",
            "react",
            "vue",
            "onclick=\"pause",
            "onclick=\"resume",
            "onclick=\"retry",
        ]
        for token in forbidden_html:
            self.assertNotIn(token, html.lower())

        forbidden_source = [
            "fetch(\"/run",
            "fetch('/run",
            "pauseAgent",
            "resumeAgent",
            "retryAgent",
            "editGoal",
        ]
        for token in forbidden_source:
            self.assertNotIn(token, source)

    def test_v0_4_viewer_uses_prototype_hierarchy_classes(self) -> None:
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn('class="summary-panel"', html)
        self.assertIn('class="context-panel original-request"', html)
        self.assertIn('class="context-panel result"', html)
        self.assertIn("round-index", source)
        self.assertIn("round-status-dot", source)
        self.assertIn("round-step-count", source)
        self.assertIn("step-io-grid", source)
        self.assertIn("raw-event", source)
        self.assertIn(".summary-value", css)
        self.assertIn(".round-index", css)
        self.assertIn(".step-io-grid", css)
        self.assertIn(".raw-event", css)

    def test_v0_4_viewer_explains_task_entry_and_round_flow(self) -> None:
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("function runStartedEvent", source)
        self.assertIn("function renderTaskEntryItem", source)
        self.assertIn("function renderTaskEntryDetail", source)
        self.assertIn("function renderFlowOverview", source)
        self.assertIn("function buildFlowItems", source)
        self.assertIn("任务入口", source)
        self.assertIn("本轮流程", source)
        self.assertIn("Tool:", source)
        self.assertIn("Final Answer", source)
        self.assertIn("Complete", source)
        self.assertIn(".task-entry", css)
        self.assertIn(".flow-overview", css)
        self.assertIn(".flow-node", css)

    def test_task_entry_nav_uses_entry_marker_not_raw_event_step(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn('roundIndex.textContent = "0"', source)

        entry_start = source.index("function renderTaskEntryItem")
        entry_end = source.index("function renderTaskCompletionItem", entry_start)
        entry_body = source[entry_start:entry_end]
        self.assertNotIn("roundIndex.textContent = String(event.step)", entry_body)

    def test_v0_4_viewer_explains_task_completion_separately(self) -> None:
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("function terminalEvent", source)
        self.assertIn("function shouldShowTerminalEvent", source)
        self.assertIn("function renderTaskCompletionItem", source)
        self.assertIn("function renderTaskCompletionDetail", source)
        self.assertIn("整次运行完成", source)
        self.assertIn("Run Completed", source)
        self.assertIn("run_completed", source)
        self.assertIn("run_failed", source)
        self.assertIn("task-completion", source)
        self.assertIn(".task-completion", css)

    def test_task_completion_nav_uses_display_index_not_raw_event_step(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("rounds[rounds.length - 1].index + 1", source)
        self.assertIn("renderTaskCompletionItem(roundList, completion, completionDisplayIndex)", source)
        self.assertIn("function renderTaskCompletionItem(roundList, event, displayIndex)", source)
        self.assertIn("roundIndex.textContent = String(displayIndex)", source)

        completion_start = source.index("function renderTaskCompletionItem")
        completion_end = source.index("function renderRoundDetail", completion_start)
        completion_body = source[completion_start:completion_end]
        self.assertNotIn("roundIndex.textContent = String(event.step)", completion_body)

    def test_planned_rounds_only_include_events_for_selected_task(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        filter_start = source.index("function roundsForSelectedTask")
        filter_end = source.index("function shouldShowTerminalEvent", filter_start)
        filter_body = source[filter_start:filter_end]

        self.assertIn("event.task_id === state.selectedTaskId", filter_body)
        self.assertIn("return enrichRound({ ...round, events })", filter_body)

        selected_start = source.index("function selectedRound")
        selected_end = source.index("function runStartedEvent", selected_start)
        selected_body = source[selected_start:selected_end]
        self.assertIn("rounds = roundsForSelectedTask(rounds)", selected_body)

    def test_terminal_result_is_attached_to_last_planned_task(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("plan.definitions[plan.definitions.length - 1].task_id", source)
        self.assertIn("shouldShowTerminalEvent(plan) ? terminalEvent() : null", source)
        self.assertIn("state.selectedTaskId === lastTask.task_id", source)
        self.assertIn("整次运行完成", source)

    def test_planned_task_entry_uses_its_own_task_started_event(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("function taskEntryEvent(plan)", source)
        self.assertIn('event.phase === "task_started" && event.task_id === state.selectedTaskId', source)
        self.assertIn("const entry = taskEntryEvent(plan)", source)
        self.assertIn('title.textContent = isPlannedTaskEntry ? "任务开始" : "任务入口"', source)
        self.assertIn('return ["Task Plan", "Task Started"]', source)


    def test_v0_5_viewer_handles_permission_phases(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("permission_requested", source)
        self.assertIn("permission_resolved", source)
        self.assertIn("Permission Request", source)
        self.assertIn("User Approved", source)
        self.assertIn("User Rejected", source)
        self.assertIn('"tool_started"', source)
        self.assertIn("event.input?.tool_name", source)

    def test_v0_5_permission_events_do_not_start_rounds(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        build_rounds_start = source.index("function buildRounds")
        build_rounds_end = source.index("function enrichRound", build_rounds_start)
        build_rounds_body = source[build_rounds_start:build_rounds_end]

        phases_that_start_rounds = ["context_built"]
        for phase in phases_that_start_rounds:
            self.assertIn(phase, build_rounds_body)

        phases_that_do_not_start_rounds = [
            "permission_requested",
            "permission_resolved",
            "run_started",
            "run_completed",
            "run_failed",
            "run_interrupted",
        ]
        phase_check_lines = [
            line.strip()
            for line in build_rounds_body.splitlines()
            if line.strip().startswith('if (event.phase === "')
        ]
        starting_phases = [
            line.split('"')[1]
            for line in phase_check_lines
        ]
        for phase in phases_that_do_not_start_rounds:
            self.assertNotIn(phase, starting_phases)

    def test_v0_5_preserves_existing_v4_structure_tokens(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")

        v0_4_tokens = [
            "task-entry",
            "task-completion",
            "flow-overview",
            "summary-panel",
            "context-panel",
            "round-index",
            "round-status-dot",
            "round-step-count",
            "step-io-grid",
            "raw-event",
            "flow-node",
        ]

        for token in v0_4_tokens:
            found = token in source or token in html or token in css
            self.assertTrue(found, f"V0.4 token '{token}' no longer present after V0.5 changes")

    def test_v0_5_does_not_add_approve_reject_buttons(self) -> None:
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        forbidden = [
            "onclick=\"approve",
            "onclick=\"reject",
            "onclick='approve",
            "onclick='reject",
            "approveButton",
            "rejectButton",
            "id=\"approve",
            "id=\"reject",
        ]
        for token in forbidden:
            self.assertNotIn(token, html.lower())
            self.assertNotIn(token, source)


class V06TraceViewerSourceTest(unittest.TestCase):
    def test_summary_grid_replaces_observations_with_context_builds(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")

        # buildRunSummary should have contextBuilds, not observations:
        build_start = js.index("function buildRunSummary")
        render_summary_start = js.index("function renderRunSummary", build_start)
        build_body = js[build_start:render_summary_start]
        self.assertIn("contextBuilds", build_body)
        self.assertIn('phase === "context_built"', build_body)
        self.assertNotIn("observations:", build_body)

        # renderRunSummary should have "上下文构建", not "观察结果"
        render_end = js.index("function buildRounds", render_summary_start)
        render_body = js[render_summary_start:render_end]
        self.assertIn('"上下文构建"', render_body)
        self.assertNotIn('"观察结果"', render_body)
        # exactly 5 items
        self.assertIn('["Agentic Loop 轮次"', render_body)
        self.assertIn('["模型决策"', render_body)
        self.assertIn('["工具调用"', render_body)
        self.assertIn('["上下文构建"', render_body)
        self.assertIn('["权限确认"', render_body)

        # CSS .run-summary-grid should still be 5 columns
        self.assertIn("grid-template-columns: repeat(5, minmax(0, 1fr))", css)

    def test_render_context_built_has_seven_source_cards(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        # renderContextBuiltStep must exist
        self.assertIn("function renderContextBuiltStep", js)

        # Must mention 7 类上下文
        self.assertIn("本轮模型将使用 7 类上下文", js)

        # Must have all 7 data-source values
        expected_sources = [
            "goal",
            "workspace-config",
            "run-memory",
            "run-metadata",
            "tool-catalog",
            "observations",
            "project-content",
        ]
        for source in expected_sources:
            self.assertIn(f'source: "{source}"', js)

        # Must NOT use .step-io-grid for context_built
        # The context_built branch in renderEventStep should call renderContextBuiltStep
        render_step_start = js.index("function renderEventStep")
        render_step_end = js.index("function renderModelDecisionStep", render_step_start)
        render_step_body = js[render_step_start:render_step_end]
        self.assertIn("renderContextBuiltStep(step, event, state.events)", render_step_body)

    def test_context_source_cards_have_independent_scroll(self) -> None:
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")

        self.assertIn(".context-source-body", css)
        self.assertIn("overflow-y: auto", css)
        self.assertIn("overscroll-behavior: contain", css)

        # Desktop: 2 columns
        self.assertIn("grid-template-columns: repeat(2, minmax(0, 1fr))", css)

        # Narrow: single column
        # Find the media query section and check context-source-grid becomes 1fr
        media_start = css.index("@media (max-width: 800px)")
        media_body = css[media_start:]
        self.assertIn(".context-source-grid", media_body)
        self.assertIn("grid-template-columns: 1fr", media_body)

        # goal should span 2 cols on desktop, auto on narrow
        self.assertIn('.context-source-card[data-source="goal"]', css)
        self.assertIn("grid-column: 1 / -1", css)
        self.assertIn("grid-column: auto", media_body)

    def test_context_source_cards_render_status_and_raw_details(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("context-source-status", js)
        self.assertIn("priority", js)
        self.assertIn("loaded", js)
        self.assertIn("permission", js)

        # raw JSON uses <details> without open
        self.assertIn('document.createElement("details")', js)
        self.assertIn('"raw-context"', js)
        self.assertIn("原始 Context JSON", js)

        # uses textContent, not innerHTML
        self.assertNotIn("innerHTML", js)

    def test_task_entry_uses_zero_index_once(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        # renderTaskEntryItem should use "0"
        entry_start = js.index("function renderTaskEntryItem")
        entry_end = js.index("function renderTaskCompletionItem", entry_start)
        entry_body = js[entry_start:entry_end]
        self.assertIn('roundIndex.textContent = "0"', entry_body)

        # buildRounds should still skip run_started
        rounds_start = js.index("function buildRounds")
        rounds_end = js.index("function enrichRound", rounds_start)
        rounds_body = js[rounds_start:rounds_end]
        self.assertIn('"run_started"', rounds_body)
        self.assertIn("continue", rounds_body)

        # Should not have id: "round-0"
        self.assertNotIn('"round-0"', js)

    def test_context_change_is_computed(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("function buildContextChange", js)

        # Should compare adjacent context_built snapshots
        change_start = js.index("function buildContextChange")
        change_end = js.index("function renderContextBuiltStep", change_start)
        change_body = js[change_start:change_end]
        self.assertIn("item.step < event.step", change_body)
        self.assertIn("previous.output?.observations", change_body)
        self.assertIn("previous.output?.selected_project_content", change_body)
        self.assertIn("首轮，无前序上下文", change_body)

    def test_flow_uses_context_build_label(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        # buildFlowItems context_built branch uses "Context Build"
        flow_start = js.index("function buildFlowItems")
        flow_end = js.index("function createContextSourceCard", flow_start)
        flow_body = js[flow_start:flow_end]
        self.assertIn('add("Context Build")', flow_body)
        self.assertNotIn('add("Context")', flow_body)

        # moduleForPhase still has "context_built": "Context"
        module_start = js.index("function moduleForPhase")
        module_end = js.index("function renderOriginalRequest", module_start)
        module_body = js[module_start:module_end]
        self.assertIn('"context_built": "Context"', module_body)

    def test_no_static_context_panel(self) -> None:
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")

        self.assertNotIn('id="context-sources"', html)
        self.assertNotIn('id="context-detail"', html)

        # #original-request before #run-summary before #final-answer before #round-list
        req_pos = html.index('id="original-request"')
        summary_pos = html.index('id="run-summary"')
        final_pos = html.index('id="final-answer"')
        list_pos = html.index('id="round-list"')
        self.assertLess(req_pos, summary_pos)
        self.assertLess(summary_pos, final_pos)
        self.assertLess(final_pos, list_pos)

    def test_key_dom_ids_present(self) -> None:
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        # HTML key ids
        for id_name in ["run-summary", "original-request", "final-answer", "round-list", "round-detail"]:
            self.assertIn(f'id="{id_name}"', html)

        # CSS existing classes
        for class_name in [".round-list", ".flow-overview", ".flow-node", ".event-step"]:
            self.assertIn(class_name, css)

        # CSS new V0.6 classes
        for class_name in [
            ".context-build-intro",
            ".context-source-grid",
            ".context-source-card",
            ".context-source-body",
            ".context-change",
            ".raw-context",
        ]:
            self.assertIn(class_name, css)

        # JS new V0.6 functions
        for func_name in [
            "createContextSourceCard",
            "createContextSourceGroup",
            "buildContextChange",
            "renderContextBuiltStep",
        ]:
            self.assertIn(func_name, js)

    def test_build_context_change_handles_object_entries(self) -> None:
        """兼容开发期旧记录中的 {path, preview} 条目。"""
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        path_start = js.index("function selectedProjectPath")
        path_end = js.index("function buildSelectedProjectContentText", path_start)
        path_body = js[path_start:path_end]
        change_start = js.index("function buildContextChange")
        change_end = js.index("function renderContextBuiltStep", change_start)
        change_body = js[change_start:change_end]

        self.assertIn("entry.path", path_body)
        self.assertIn('typeof entry === "object"', path_body)
        self.assertIn("previousEntries.map(selectedProjectPath)", change_body)
        self.assertIn("currentFiles\n        .map(selectedProjectPath)", change_body)

        # 不应再用字符串比较
        self.assertNotIn("!previousFiles.has(path)", change_body.replace(
            "!previousPaths.has(path)", "REMOVED"))

    def test_project_content_uses_full_read_file_observation_content(self) -> None:
        """Selected Project Content 必须展示 read_file 的完整正文，而不是 200 字预览。"""
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("function buildSelectedProjectContentText", js)
        helper_start = js.index("function buildSelectedProjectContentText")
        helper_end = js.index("function buildContextChange", helper_start)
        helper_body = js[helper_start:helper_end]

        self.assertIn('observation.tool_name === "read_file"', helper_body)
        self.assertIn("observation.result?.success", helper_body)
        self.assertIn("observation.result?.content", helper_body)
        self.assertNotIn("entry.preview", helper_body)

        render_start = js.index("function renderContextBuiltStep")
        render_end = js.index("function renderEventStep", render_start)
        render_body = js[render_start:render_end]
        self.assertIn("buildSelectedProjectContentText(output)", render_body)


class V07TraceViewerSourceTest(unittest.TestCase):
    """V0.7: command step rendering without regressing V0.4–V0.6."""

    def test_build_display_steps_function_exists(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        self.assertIn("function buildDisplaySteps", js)

    def test_render_command_step_function_exists(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        self.assertIn("function renderCommandStep", js)

    def test_is_run_command_start_helper_exists(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        self.assertIn("isRunCommandStart", js)

    def test_command_step_css_classes_present(self) -> None:
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")
        self.assertIn(".command-step", css)
        self.assertIn(".command-label", css)

    def test_command_labels_in_source(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        self.assertIn("预定义动作", js)
        self.assertIn("实际命令", js)
        self.assertIn("工作目录", js)
        self.assertIn("exit_code", js)
        self.assertIn("duration_ms", js)
        self.assertIn("stdout", js)
        self.assertIn("stderr", js)

    def test_build_flow_items_still_renders_tool_run_command(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        flow_start = js.index("function buildFlowItems")
        flow_end = js.index("function createContextSourceCard", flow_start)
        flow_body = js[flow_start:flow_end]
        self.assertIn('Tool:', flow_body)
        self.assertIn('event.input?.tool_name', flow_body)

    def test_all_seven_v06_context_source_tokens_remain(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        expected_sources = [
            "goal",
            "workspace-config",
            "run-memory",
            "run-metadata",
            "tool-catalog",
            "observations",
            "project-content",
        ]
        for source in expected_sources:
            self.assertIn(f'source: "{source}"', js)

    def test_no_approve_reject_input_in_source(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        forbidden = ["approveButton", "rejectButton", "command-input", "id=\"approve", "id=\"reject"]
        for token in forbidden:
            self.assertNotIn(token, js)

    def test_build_display_steps_pairs_command_events(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        self.assertIn("tool_started", js)
        self.assertIn("tool_finished", js)
        # buildDisplaySteps should reference kind: "command"
        self.assertIn('"command"', js)

    def test_command_step_uses_textcontent_not_innerhtml(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        # The whole file should not use innerHTML (V0.6 rule, still applies)
        self.assertNotIn("innerHTML", js)

    def test_v06_v05_v04_preservation(self) -> None:
        """Cross-check: V0.4–V0.6 tokens must still be present."""
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")

        v0_4_tokens = [
            "task-entry", "task-completion", "flow-overview",
            "summary-panel", "context-panel", "round-index",
            "round-status-dot", "round-step-count", "step-io-grid",
            "raw-event", "flow-node",
        ]
        for token in v0_4_tokens:
            found = token in js or token in html or token in css
            self.assertTrue(found, f"V0.4 token '{token}' no longer present")

        v0_6_tokens = [
            "context-build-intro", "context-source-grid", "context-source-card",
            "context-source-body", "context-change", "raw-context",
            "createContextSourceCard", "buildContextChange", "renderContextBuiltStep",
            "本轮模型将使用 7 类上下文",
        ]
        for token in v0_6_tokens:
            found = token in js or token in html or token in css
            self.assertTrue(found, f"V0.6 token '{token}' no longer present")


if __name__ == "__main__":
    unittest.main()


# ===== V0.8 Trace Viewer 源码测试 =====


class V08TraceViewerSourceTest(unittest.TestCase):
    def test_dom_order_matches_frozen_prototype(self) -> None:
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")

        # 模块顺序：run-status → summary-panel → original-request → result-panel → task-plan-panel → layout
        self.assertIn('id="task-plan-panel"', html)
        self.assertIn('id="selected-task-label"', html)

        req_pos = html.index('id="original-request"')
        result_pos = html.index('id="final-answer"')
        plan_pos = html.index('id="task-plan-panel"')
        layout_pos = html.index('class="layout"')

        self.assertLess(req_pos, result_pos)
        self.assertLess(result_pos, plan_pos)
        self.assertLess(plan_pos, layout_pos)

    def test_task_plan_panel_has_required_structure(self) -> None:
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")

        self.assertIn('id="task-plan-panel"', html)
        self.assertIn('class="task-plan-panel"', html)
        self.assertIn("hidden", html)
        self.assertIn('id="task-progress-text"', html)
        self.assertIn('id="task-list"', html)
        self.assertIn('class="task-list"', html)
        panel = html[html.index('id="task-plan-panel"'):html.index('class="layout"')]
        for artifact_id in ["task-artifact-panel", "task-artifact-title", "task-artifact-status", "task-artifact-body"]:
            self.assertIn(artifact_id, panel)

    def test_selected_task_label_in_rounds_panel(self) -> None:
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")

        self.assertIn('id="selected-task-label"', html)
        # 初始隐藏
        rounds_section_start = html.index('id="round-list"')
        rounds_section_before = html[rounds_section_start - 200:rounds_section_start]
        self.assertIn("hidden", rounds_section_before)

    def test_task_plan_js_functions_exist(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("buildTaskPlan", js)
        self.assertIn("renderTaskPlan", js)
        self.assertIn("selectTask", js)
        self.assertIn("roundsForSelectedTask", js)
        self.assertIn("selectedTaskId", js)
        for function in ["buildTaskArtifacts", "artifactForTask", "renderSelectedTaskArtifact", "formatArtifactEvidence"]:
            self.assertIn(function, js)
        self.assertIn("renderArtifactChips", js)
        self.assertIn("artifact-flow", js)
        self.assertIn("artifact-chip", js)

    def test_task_plan_progress_value_tracks_completed_tasks(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("const progressValue = document.querySelector(\"#task-progress-value\")", js)
        self.assertIn("const progressPercent = plan.totalCount ? (plan.completedCount / plan.totalCount) * 100 : 0", js)
        self.assertIn("progressValue.style.width = `${progressPercent}%`", js)

    def test_v0_9_artifact_detail_matches_frozen_prototype_structure(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")

        render_start = js.index("function renderSelectedTaskArtifact")
        render_end = js.index("function selectTask", render_start)
        render_body = js[render_start:render_end]

        for token in [
            "artifact-grid",
            "artifact-section",
            "artifact-content",
            "artifact-evidence",
            "evidence-list",
            "artifact-flow",
        ]:
            self.assertIn(token, render_body)

        self.assertIn(".task-plan-panel .artifact-grid", css)
        self.assertIn("minmax(0, 1.4fr) minmax(280px, 0.8fr)", css)
        self.assertIn(".task-plan-panel .artifact-section", css)
        self.assertIn(".task-plan-panel .evidence-list", css)
        self.assertNotIn(".artifact-content { grid-column: 1 / -1; }", css)

    def test_v0_9_artifact_responsive_rules_are_scoped(self) -> None:
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")

        desktop_breakpoint = css.index("@media (max-width: 1050px)")
        narrow_breakpoint = css.index("@media (max-width: 760px)", desktop_breakpoint)
        desktop_rules = css[desktop_breakpoint:narrow_breakpoint]
        narrow_rules = css[narrow_breakpoint:]

        self.assertIn(".task-plan-panel .artifact-grid", desktop_rules)
        self.assertIn("grid-template-columns: 1fr", desktop_rules)
        self.assertIn(".task-plan-panel .artifact-flow", narrow_rules)
        self.assertIn("grid-template-columns: 1fr", narrow_rules)

    def test_task_plan_css_classes_exist(self) -> None:
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")

        self.assertIn(".task-plan-panel", css)
        self.assertIn(".task-card", css)
        self.assertIn(".task-list", css)
        self.assertIn(".selected-task-label", css)
        self.assertIn(".artifact-flow", css)
        self.assertIn(".artifact-chip", css)

    def test_css_custom_properties_for_task_states(self) -> None:
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")

        for var_name in ["--blue", "--blue-soft", "--green", "--green-soft", "--red", "--red-soft"]:
            self.assertIn(var_name, css, f"CSS custom property {var_name} must be defined")

    def test_no_forms_or_approve_reject_controls(self) -> None:
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        forbidden_html = ["<form", "<input", "<select", "<textarea", "approve", "reject", "retry", "onclick=\"edit"]
        for token in forbidden_html:
            self.assertNotIn(token, html.lower())

        forbidden_js = ["approveButton", "rejectButton", "retryAgent", "editGoal", "executeButton"]
        for token in forbidden_js:
            self.assertNotIn(token, js)

    def test_v07_v06_v05_v04_preservation(self) -> None:
        js = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")
        html = (ROOT / "web" / "trace_viewer.html").read_text(encoding="utf-8")
        css = (ROOT / "web" / "trace_viewer.css").read_text(encoding="utf-8")

        v0_4_tokens = [
            "task-entry", "task-completion", "flow-overview",
            "summary-panel", "context-panel", "round-index",
            "round-status-dot", "round-step-count", "step-io-grid",
            "raw-event", "flow-node",
        ]
        for token in v0_4_tokens:
            found = token in js or token in html or token in css
            self.assertTrue(found, f"V0.4 token '{token}' no longer present")

        v0_7_tokens = [
            "command-step", "command-label", "isRunCommandStart",
            "buildDisplaySteps", "renderCommandStep",
        ]
        for token in v0_7_tokens:
            found = token in js or token in html or token in css
            self.assertTrue(found, f"V0.7 token '{token}' no longer present")


class TraceViewerCoreContractTest(unittest.TestCase):
    def test_core_exposes_reusable_instance_api(self) -> None:
        source = (ROOT / "web" / "trace_viewer_core.js").read_text(encoding="utf-8")

        self.assertIn("window.MinAgentTraceViewer = { create }", source)
        for member in ("loadRun", "applyEvent", "setConnectionStatus", "reset", "destroy"):
            self.assertIn(member, source)
        self.assertIn("const document = {", source)
        self.assertIn("querySelector: root.querySelector.bind(root)", source)

    def test_legacy_wrapper_owns_only_sse_connection(self) -> None:
        wrapper = (ROOT / "web" / "trace_viewer.js").read_text(encoding="utf-8")

        self.assertIn('window.MinAgentTraceViewer.create({ root })', wrapper)
        self.assertIn('new EventSource("/events")', wrapper)
        self.assertNotIn("function buildTaskPlan", wrapper)
        self.assertNotIn("function buildRounds", wrapper)
        self.assertNotIn("function renderTaskPlan", wrapper)
