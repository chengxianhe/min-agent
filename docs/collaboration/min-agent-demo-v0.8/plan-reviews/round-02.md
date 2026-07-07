# Plan Review Round 2

## Metadata

- `attempts`: `1`
- `cost_usd`: `0.364343`
- `task_id`: `min-agent-demo-v0.8`

## Normalized result

```json
{
  "findings": [
    {
      "evidence": "Task 2 Step 3 says `complete_current()` requires `result.success is True` on cited Observations. Task 4 Step 5 says `TaskPlan.complete_current` verifies \"the cited Observation indexes and results.\" But neither the state machine nor the Agent Loop checks whether the actual tool output semantically satisfies the free-text `completion_criteria` field. The product design says '任务状态必须由真实 Execution 结果驱动，不能仅由模型声称完成' but this only prevents model imagination — it doesn't prevent the model from citing a successful but irrelevant Observation (e.g., citing a `list_dir` success to complete a 'write summary.md' task).",
      "id": "F01",
      "recommendation": "Either (a) accept this as a known limitation and document it in product-design.md and implementation-plan.md as 'V0.8 validates structural evidence (real tool call succeeded within the task), not semantic criteria matching — that remains the model's responsibility,' or (b) add a `completion_criteria` validation hook in `TaskPlan` that at minimum asserts the cited tool types are plausible for the criteria. Option (a) is more appropriate for V0.8's scope given the 'not production' boundary.",
      "severity": "P1",
      "title": "Completion criteria validation is structural (Observation indexes + success), not semantic"
    },
    {
      "evidence": "Task 4 Step 5 guard: '`create_plan` is legal only when no plan exists and no tool Observation exists.' Product design says '计划在首次工具调用前完整生成.' The implementation guard checks for Observation existence, not tool-call initiation. If a tool starts but the observation_added event is delayed (unlikely in current architecture but possible in async scenarios), `create_plan` could be accepted after a tool has already started. This is a low-probability edge case in the current synchronous loop but contradicts the product design's explicit '首次工具调用前' constraint.",
      "id": "F02",
      "recommendation": "Change the guard to track whether any `tool_started` event has been emitted in the current run, rather than relying on Observation existence. Add a test case in Task 4 Step 2 that asserts `create_plan` is rejected after a tool call was made (even if succeeded).",
      "severity": "P1",
      "title": "`create_plan` after tool-start but before observation_added is not explicitly blocked"
    },
    {
      "evidence": "Task 8 Step 2 lists `taskIdForRound(events)` — the function name suggests it takes a round but the parameter is named `events`. Looking at the description 'associate plan creation with task-1 and normal rounds by event.task_id,' this seems like a helper that maps events to tasks, not rounds.",
      "id": "F03",
      "recommendation": "Rename to `taskIdForEvents(events)` or `findTaskIdByEvents(events)`, or rename the parameter to `roundEvents` if the intent is to process a single round's event list. Update test assertions accordingly.",
      "severity": "P2",
      "title": "`taskIdForRound` function signature in Task 8 Step 2 is misleading"
    },
    {
      "evidence": "Task 6 Step 3 prompt tests assert the prompt says 'do not change task definitions after creation' but not 'do not create a new plan if one already exists.' The Agent Loop preflight check (Task 4 Step 5) rejects a second `create_plan` at the local level, but the model could waste a turn proposing one. Contrast with `complete_task` for wrong task-id which is explicitly tested in Task 4 Step 2 test 3.",
      "id": "F04",
      "recommendation": "Add a prompt instruction in `src/min_agent/deepseek_llm.py` telling the model: 'A plan already exists for this run. Do not propose another `create_plan`. Act only on `current_task_id`.' Mirror this in FakeLLM's `_decide_planned_goal` path.",
      "severity": "P2",
      "title": "No explicit DeepSeek prompt instruction to reject `create_plan` when a plan already exists"
    },
    {
      "evidence": "Task 8 Step 2 tests cover `buildTaskPlan`, `renderTaskPlan`, `selectTask`, `roundsForSelectedTask`, and `taskIdForRound`. The `#selected-task-label` is required in Step 1's DOM contract but only tested for initial hidden state. There is no test asserting it shows when a task is selected and hides when switching to simple mode, despite the prototype's explicit `hidden` toggling in `renderMode()`.",
      "id": "F05",
      "recommendation": "Add a test in `tests/test_trace_viewer_source.py` that asserts `#selected-task-label` is not hidden when `#task-plan-panel` is visible and `selectedTaskId` is set, and is hidden when `#task-plan-panel` is hidden or `selectedTaskId` is null.",
      "severity": "P2",
      "title": "Trace Viewer: no explicit source test for `selectedTaskLabel` hidden/shown lifecycle during plan completion"
    },
    {
      "evidence": "Task 8 Step 6: 'Port the relevant `.task-plan-*`, `.task-card.*`, `.task-status`, `.task-error`, `.selected-task-label`, progress bar, 2-column tablet, and 1-column mobile rules from `docs/superpowers/v0.8/trace-viewer-prototype.html`.' The prototype CSS defines ~150 lines of rules, but many (like `.status`, `.summary-panel`, `.badge`, `.event-step`) already exist in the current `web/trace_viewer.css`. There is no distinction between 'new V0.8 rules' and 'prototype rules that duplicate existing CSS.'",
      "id": "F06",
      "recommendation": "Specify exactly which CSS selectors from the prototype are new for V0.8 and must be ported: `.task-plan-panel`, `.task-plan-heading`, `.task-progress`, `.progress-track`, `.progress-value`, `.task-list`, `.task-card.*`, `.task-index`, `.task-status`, `.task-top`, `.task-error`, `.selected-task-label`, and the updated `@media (max-width: 760px)` rules for `.task-list` and `.task-progress`. The executor should diff against existing `web/trace_viewer.css` before applying.",
      "severity": "P3",
      "title": "Implementation plan Task 8 Step 6 says 'port the relevant CSS rules' but doesn't define 'relevant'"
    },
    {
      "evidence": "Task 11 Step 5: 'At approximately 390 px width, confirm one-column task cards, stacked round/detail regions, readable content, and no horizontal page overflow.' The prototype CSS uses `@media (max-width: 760px)` for the single-column layout, which already applies at 390px. However, there is no explicit 390px breakpoint or test for very narrow viewports (e.g., text overflow at 390px is not the same as at 760px).",
      "id": "F07",
      "recommendation": "Either (a) add a `@media (max-width: 520px)` breakpoint with specific narrow-viewport rules (reduced padding, smaller font sizes) and test at 390px, or (b) change the acceptance criterion to '760px' to match the actual breakpoint. Option (b) is simpler for V0.8 scope.",
      "severity": "P3",
      "title": "Task 11 browser acceptance asks for 'approximately 390 px' but prototype CSS breakpoints are 1050px and 760px"
    }
  ],
  "pass": true,
  "schema_version": 1,
  "stage": "plan_review",
  "summary": "The implementation plan is comprehensive, well-structured, and fully aligned with both the product design and project rules in AGENTS.md. All 11 tasks are defined with clear RED/GREEN test-first discipline. Security boundaries (ToolRegistry, permission chains, workspace limits) are explicitly preserved. Failure handling covers the first-failure-stop contract with detailed test cases for tool errors, permission rejection, invalid completion claims, budget exhaustion, and simple-path regression. Edge cases around Observation ownership and task-id scoping are mostly addressed. No P0 blockers. Two P1 issues around the semantic gap in completion-criteria validation and a potential preflight ambiguity, plus minor P2 edge cases in the Trace Viewer API."
}
```
