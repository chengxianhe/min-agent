# min-agent-demo V0.9 Observable Task Artifacts Implementation Plan

> **For DeepSeek executor:** Execute this plan task by task in the listed order. Use test-first changes and preserve every frozen boundary in this document. Do not use subagents, merge tasks, skip RED/GREEN verification, delete files, clean generated files, commit, push, merge, rebase, reset, tag, install dependencies, modify `.env`, or change CI/CD without separate user authorization.

**Goal:** Add observable task artifacts and explicit cross-task artifact inheritance to composite runs while keeping simple runs and every Trace Viewer area outside `#task-plan-panel` unchanged.

**Architecture:** Extend the existing V0.8 task-plan state machine so a valid `complete_task` action atomically completes the current task and stores one validated `TaskArtifact`. The Agent Loop passes only current-task Observations and current-task selected project content as working context, while completed prior artifacts are injected separately as `Inherited Task Artifacts`. Trace events remain the only Viewer data source; the Viewer adds artifact details only inside the existing task-plan panel.

**Tech Stack:** Python 3.10+ standard library (`dataclasses`, `typing`, `unittest`), existing FakeLLM and DeepSeek Chat Completions JSON adapter, existing `TraceRecorder` and SSE server, vanilla HTML/CSS/JavaScript Trace Viewer.

---

## 1. Frozen inputs and execution contract

Read these files completely before changing implementation:

```text
AGENTS.md
docs/superpowers/v0.9/product-design.md
docs/superpowers/v0.9/trace-viewer-prototype.html
docs/superpowers/v0.9/implementation-plan.md
```

Also inspect the current implementation and tests before editing:

```text
src/min_agent/types.py
src/min_agent/task_plan.py
src/min_agent/context_builder.py
src/min_agent/agent_loop.py
src/min_agent/fake_llm.py
src/min_agent/deepseek_llm.py
src/min_agent/trace_recorder.py
web/trace_viewer.html
web/trace_viewer.js
web/trace_viewer.css
tests/test_types.py
tests/test_task_plan.py
tests/test_context_builder.py
tests/test_agent_loop.py
tests/test_permission_flow.py
tests/test_fake_llm.py
tests/test_deepseek_llm.py
tests/test_cli_scenarios.py
tests/test_trace_viewer_source.py
```

Before editing, run:

```bash
git status -sb
git diff -- AGENTS.md CHANGELOG.md README.md docs/runbook.md
```

Preserve all user-owned changes. At plan-writing time, `CHANGELOG.md` was already modified and `docs/superpowers/v0.9/` was untracked; do not overwrite or revert either state.

Hard product constraints:

- V0.9 adds no tool and changes no `ToolRegistry`, workspace, `write_file`, `run_command`, or permission boundary.
- A completed planned task has exactly one available primary artifact.
- A failed or skipped task never has an available artifact and emits an explicit missing-artifact event with a reason.
- Completion evidence contains non-empty, unique, 1-based indexes into successful Observations from the current task only.
- Inherited artifacts are model inputs, never current-task completion evidence.
- Previous-task raw Observations and selected file content must not leak into the next task.
- FakeLLM must remove `_composite_read_contents` and `_composite_time_result`; no replacement hidden cache or global variable is allowed.
- DeepSeek only proposes local `AgentAction` JSON. Local validation and `TaskPlan` own task completion and artifact storage.
- Final answers in planned runs must be based on stored artifacts, not reconstructed from global Observations or private model state.
- Trace Viewer stays read-only.
- The only permitted page change is inside `#task-plan-panel`.
- Do not move, rename, restructure, restyle, or add interactions to the status, original request, run summary, final result, execution rounds, selected-task label, or round-detail areas.
- Existing Context Build and raw-event rendering may display new fields through their current generic rendering paths; do not redesign those modules.
- Simple goals produce no plan, no artifact context, no artifact events, and no artifact UI.

If product design, prototype, and this plan conflict, stop and report the conflict. Do not choose a new product behavior independently.

## 2. Required user-visible result

The canonical composite goal is:

```text
阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。
```

Its semantic event path must be:

```text
run_started
-> context_built
-> llm_decision(create_plan)
-> plan_created
-> task_started(task-1)
-> list_dir / observation_added(task-1)
-> llm_decision(complete_task + task_artifact)
-> task_artifact_created(task-1)
-> task_completed(task-1)
-> task_started(task-2)
-> context_built(inherited_task_artifacts=[task-1])
-> read_file... / observation_added(task-2)
-> task_artifact_created(task-2)
-> task_completed(task-2)
-> task_started(task-3)
-> context_built(inherited_task_artifacts=[task-1, task-2])
-> permission_requested(run_command)
-> permission_resolved(approved=true)
-> tool_started(run_command)
-> observation_added(task-3)
-> task_artifact_created(task-3)
-> task_completed(task-3)
-> task_started(task-4)
-> context_built(inherited_task_artifacts=[task-1, task-2, task-3])
-> permission_requested(write_file)
-> permission_resolved(approved=true)
-> tool_started(write_file)
-> observation_added(task-4)
-> task_artifact_created(task-4)
-> task_completed(task-4)
-> context_built(inherited_task_artifacts=[task-1, task-2, task-3, task-4])
-> final_answer
-> run_completed
```

The task artifacts are:

| Task | Artifact title | Artifact content source | Valid evidence |
| --- | --- | --- | --- |
| `task-1` | Workspace Markdown 文件清单 | successful `list_dir` content | task-1 Observation 1 |
| `task-2` | 项目资料摘要 | successful task-2 `read_file` content | task-2 read Observations |
| `task-3` | 当前本地时间 | successful `run_command/get_current_time` content | task-3 Observation 1 |
| `task-4` | 摘要文件写入结果 | successful `write_file(summary.md)` result | task-4 write Observation |

The actual page order must remain exactly:

```text
运行状态
-> 原始需求
-> 本次任务统计
-> 最终结果
-> 任务计划
   -> 任务卡片
   -> 所选任务产物
-> 执行轮次 / 轮次详情
```

The existing `#selected-task-label` remains in the execution-rounds panel. It may keep updating when a task card is clicked, but it must not be moved into the task-plan panel as part of V0.9.

For the simple goal `现在几点？`, the V0.7 behavior remains: no plan phases, no artifact phases, no `inherited_task_artifacts` key in model context, and `#task-plan-panel` remains hidden.

## 3. Exact data contracts

Use these names and meanings consistently across Python, Trace JSON, prompts, tests, and Viewer code.

```python
TaskArtifactStatus = Literal["available", "missing"]

@dataclass(frozen=True)
class TaskArtifactDraft:
    title: str
    content: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskArtifact:
    task_id: str
    title: str
    content: str
    evidence_observation_indexes: list[int]
    created_at_step: int
    status: TaskArtifactStatus
    missing_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "content": self.content,
            "evidence_observation_indexes": list(self.evidence_observation_indexes),
            "created_at_step": self.created_at_step,
            "status": self.status,
            "missing_reason": self.missing_reason,
        }
```

`TaskArtifactDraft` is model-proposed data. `TaskArtifact` is runtime-owned data. The model never supplies `task_id`, evidence indexes, step, status, or missing reason inside `task_artifact`. Keep these two types separate in V0.9: the draft/runtime split is the trust boundary that prevents model JSON from supplying runtime-owned provenance fields.

The valid `complete_task` JSON is:

```json
{
  "kind": "complete_task",
  "task_id": "task-2",
  "completion_evidence": "Observations 1 and 2 are successful read_file results from task-2",
  "evidence_observation_indexes": [1, 2],
  "task_artifact": {
    "title": "项目资料摘要",
    "content": "min-agent-demo 是一个可观察的最小 Agent 机制演示..."
  },
  "reason": "The current completion criterion is satisfied"
}
```

An available artifact event has this output shape:

```json
{
  "artifact": {
    "task_id": "task-2",
    "title": "项目资料摘要",
    "content": "...",
    "evidence_observation_indexes": [1, 2],
    "created_at_step": 24,
    "status": "available",
    "missing_reason": ""
  },
  "evidence_observations": [
    {"index": 1, "tool_name": "read_file", "args": {"path": "project.md"}, "success": true},
    {"index": 2, "tool_name": "read_file", "args": {"path": "architecture.md"}, "success": true}
  ],
  "inherited_task_ids": ["task-1"],
  "forwarded_task_ids": ["task-3", "task-4"]
}
```

A missing artifact event has this output shape:

```json
{
  "artifact": {
    "task_id": "task-3",
    "title": "获取当前时间的任务产物",
    "content": "",
    "evidence_observation_indexes": [],
    "created_at_step": 31,
    "status": "missing",
    "missing_reason": "用户拒绝执行 run_command"
  },
  "inherited_task_ids": ["task-1", "task-2"],
  "forwarded_task_ids": []
}
```

`task_artifact_missing` for a skipped task uses an empty `inherited_task_ids` list because that task never started and never received a Context Build.

For `status="missing"`, `created_at_step` is the trace step of the `task_artifact_missing` event. It timestamps the observable missing-artifact event only; it does not claim that an artifact was created or stored in `TaskPlan`.

`forwarded_task_ids` is event-only Viewer metadata, derived from the fixed task-plan order to render the artifact's later destinations. It is not a `TaskArtifact` persisted field, is not added to model context, and is not part of `TaskPlan` state.

## 4. File responsibility map

### Modify before implementation rules

- `AGENTS.md`: add the V0.9 boundary and task-artifact rules before changing runtime code.

### Runtime and model files

- `src/min_agent/types.py`: artifact types, action payload, task snapshot artifact, context inheritance, event phases.
- `src/min_agent/trace_recorder.py`: expose the next event step safely for artifact `created_at_step` assignment.
- `src/min_agent/task_plan.py`: validate and atomically store available artifacts with completed task state.
- `src/min_agent/context_builder.py`: inject inherited artifacts as a separate dynamic context source.
- `src/min_agent/agent_loop.py`: isolate per-task dynamic context, emit artifact events, and aggregate final artifact context.
- `src/min_agent/fake_llm.py`: derive every cross-task input from inherited artifacts and remove hidden state.
- `src/min_agent/deepseek_llm.py`: strict nested artifact parsing and explicit context/prompt rules.

### Viewer files

- `web/trace_viewer.html`: add the selected-task artifact container inside `#task-plan-panel` only.
- `web/trace_viewer.js`: derive artifact state from trace events and render it when task selection changes.
- `web/trace_viewer.css`: style only the new descendants of `.task-plan-panel`, including narrow-screen behavior.

### Tests

- `tests/test_types.py`
- `tests/test_trace_recorder.py`
- `tests/test_task_plan.py`
- `tests/test_context_builder.py`
- `tests/test_agent_loop.py`
- `tests/test_fake_llm.py`
- `tests/test_deepseek_llm.py`
- `tests/test_cli_scenarios.py`
- `tests/test_trace_viewer_source.py`
- `tests/test_project_testing_rules.py` only if it explicitly checks version rule text.

### User-facing documentation after implementation

- `README.md`: V0.9 behavior and canonical scenario.
- `docs/runbook.md`: event chain, FakeLLM/DeepSeek run instructions, browser result, and cleanup status.
- `CHANGELOG.md`: add the implemented V0.9 entry while preserving existing user edits and roadmap text.

No new runtime module, dependency, database, environment file, CI change, or frontend framework is required.

## Task 1: Freeze V0.9 rules and add artifact data contracts

**Files:**

- Modify: `AGENTS.md`
- Modify: `src/min_agent/types.py`
- Modify: `src/min_agent/trace_recorder.py`
- Modify: `tests/test_types.py`
- Modify: `tests/test_trace_recorder.py`

- [ ] **Step 1: Add the V0.9 rule section to `AGENTS.md`**

Place it after the V0.8 task rules. Add this concrete section before changing runtime code:

```md
## V0.9 边界

V0.9 只增加：每个已完成计划任务的一份结构化任务产物、独立的 inherited artifacts 上下文，以及仅限任务计划模块的 Trace Viewer 产物展示。

V0.9 不增加：动态改计划、重试、恢复、并行或任务依赖图；V0.8 的权限、命令白名单和 workspace 安全边界保持不变。

## V0.9 任务产物规则

- `TaskPlan` 和运行时拥有已存储产物；模型只能提交 `title` 和 `content` 草稿。
- 完成证据只能引用当前任务成功的 Observation；继承产物不是当前任务证据。
- 前序任务的原始 Observation 和 selected project content 不得进入后续任务工作上下文。
- failed 或 skipped 任务不存入可用产物；missing 只通过 Trace 事件表达。
- `FakeLLM` 不得保留跨任务隐藏状态；跨任务信息只能来自公开上下文中的 inherited artifacts。
- Viewer 只读，页面改动只允许发生在 `#task-plan-panel` 内。
```

- [ ] **Step 2: Write failing type tests**

Add tests equivalent to:

```python
draft = TaskArtifactDraft("项目资料摘要", "summary text")
artifact = TaskArtifact(
    task_id="task-2",
    title=draft.title,
    content=draft.content,
    evidence_observation_indexes=[1, 2],
    created_at_step=12,
    status="available",
)
self.assertEqual(artifact.to_dict()["evidence_observation_indexes"], [1, 2])

snapshot = TaskSnapshot("task-2", "读取资料", "形成摘要", "completed", artifact=artifact)
self.assertEqual(snapshot.to_dict()["artifact"]["status"], "available")

action = AgentAction.complete_task(
    task_id="task-2",
    completion_evidence="read observations succeeded",
    evidence_observation_indexes=[1, 2],
    reason="criterion met",
    task_artifact=draft,
)
self.assertEqual(action.to_dict()["task_artifact"], {
    "title": "项目资料摘要",
    "content": "summary text",
})
```

Also test a V0.7 `tool_call` and `final_answer`: `task_artifact` serializes as `None`, no task plan is created, and existing fields remain unchanged.

Add `AgentContext` tests proving `inherited_task_artifacts` serializes only when `task_plan` is non-empty. A planned context with no completed predecessor serializes `"inherited_task_artifacts": []`; a simple context omits the key.

Add `TraceEvent` tests for `task_artifact_created` and `task_artifact_missing`.

- [ ] **Step 3: Write a failing recorder next-step test**

```python
recorder = TraceRecorder("goal", "/workspace", run_id="run-1")
self.assertEqual(recorder.next_step(), 1)
event = recorder.emit("run_started", "running", "start")
self.assertEqual(event.step, 1)
self.assertEqual(recorder.next_step(), 2)
```

- [ ] **Step 4: Run focused tests and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_types tests.test_trace_recorder
```

Expected: FAIL because artifact types, context fields, phases, and `next_step()` do not exist.

- [ ] **Step 5: Implement the exact contracts**

Add `TaskArtifactStatus`, `TaskArtifactDraft`, and `TaskArtifact`. Extend `TaskSnapshot` with:

```python
artifact: TaskArtifact | None = None
```

Replace `TaskSnapshot.to_dict()` with explicit nested serialization so `artifact` is either its dictionary or `None`.

Extend `AgentAction` with:

```python
task_artifact: TaskArtifactDraft | None = None
```

Append `task_artifact` after `reason` in `AgentAction.complete_task(...)` so call sites are forced to use the named argument without changing the meaning of the existing first four parameters. The method may temporarily accept `None` for compatibility, but `TaskPlan` and DeepSeek parsing must reject it before completion.

Extend `AgentContext` with:

```python
inherited_task_artifacts: list[TaskArtifact] = field(default_factory=list)
```

Inside the existing `if self.task_plan:` serialization block, always include copied `inherited_task_artifacts`.

Extend `EventPhase` with:

```python
"task_artifact_created",
"task_artifact_missing",
```

Add to `TraceRecorder`:

```python
def next_step(self) -> int:
    with self._lock:
        return len(self.events) + 1
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run the Step 4 command. Expected: PASS.

- [ ] **Step 7: Inspect scope**

```bash
git diff -- AGENTS.md src/min_agent/types.py src/min_agent/trace_recorder.py tests/test_types.py tests/test_trace_recorder.py
```

Do not commit.

## Task 2: Make task completion and artifact storage atomic

**Files:**

- Modify: `src/min_agent/task_plan.py`
- Modify: `tests/test_task_plan.py`

- [ ] **Step 1: Write failing success tests**

Update valid completion calls to supply `TaskArtifactDraft`. Assert:

```python
completed, artifact = plan.complete_current(
    task_id="task-1",
    completion_evidence="list_dir succeeded",
    evidence_observation_indexes=[1],
    observations=[Observation("list_dir", {"path": "."}, ToolResult(success=True, content="project.md"))],
    task_artifact=TaskArtifactDraft("Workspace Markdown 文件清单", "project.md"),
    created_at_step=9,
)
self.assertEqual(completed.status, "completed")
self.assertEqual(artifact.status, "available")
self.assertEqual(artifact.created_at_step, 9)
self.assertEqual(plan.artifacts(), [artifact])
self.assertEqual(plan.snapshot()[0].artifact, artifact)
```

Complete two tasks and assert `artifacts()` returns them in plan order, even if a caller mutates the returned list.

- [ ] **Step 2: Write failing validation and atomicity tests**

For each case below, call `complete_current`, assert `TaskPlanError`, then assert the task is still `running` and `artifacts()` is still empty:

- `task_artifact is None`.
- blank artifact title.
- blank artifact content.
- zero, negative, boolean, or non-integer `created_at_step`.
- empty, duplicate, boolean, zero, negative, out-of-range, or failed Observation index.
- wrong task ID or blank completion evidence.

Retain the V0.8 structural-evidence boundary test: semantic relevance is not inferred by `TaskPlan`; scenario tests enforce that the chosen Observation is relevant.

Add failure tests proving `fail_current()` leaves `artifacts()` empty for failed and skipped tasks.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_task_plan
```

Expected: FAIL because `complete_current` does not accept or store artifacts.

- [ ] **Step 4: Implement artifact ownership in `TaskPlan`**

Add:

```python
self._artifacts: dict[str, TaskArtifact] = {}
```

Add public queries:

```python
def artifacts(self) -> list[TaskArtifact]:
    return [self._artifacts[d.task_id] for d in self._definitions if d.task_id in self._artifacts]

def artifact_for(self, task_id: str) -> TaskArtifact | None:
    return self._artifacts.get(task_id)
```

`snapshot()` includes `artifact=self._artifacts.get(d.task_id)`.

Change `complete_current` to return `tuple[TaskSnapshot, TaskArtifact]`. Validate the task, evidence, draft, and step fully before mutating either `_statuses` or `_artifacts`. After all validation passes, construct one available artifact, assign it, set status to completed, and return both values.

Do not store `missing` artifacts in `TaskPlan`; failed and skipped tasks have `artifact=None`. The Agent Loop creates missing-event payloads for observability.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 3 command. Expected: PASS.

- [ ] **Step 6: Run the lower-layer suite**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_types tests.test_trace_recorder tests.test_task_plan
```

Expected: PASS.

## Task 3: Separate current-task context from inherited artifacts

**Files:**

- Modify: `src/min_agent/context_builder.py`
- Modify: `tests/test_context_builder.py`

- [ ] **Step 1: Write failing planned-context tests**

Build a planned context with one completed artifact and assert:

```python
context = builder.build(
    user_goal="composite",
    workspace="/workspace",
    available_tools=[],
    observations=current_task_observations,
    selected_project_content=["architecture.md"],
    task_plan=task_plan,
    current_task_id="task-3",
    inherited_task_artifacts=[artifact],
)
self.assertEqual(context.observations, current_task_observations)
self.assertEqual(context.selected_project_content, ["architecture.md"])
self.assertEqual(context.inherited_task_artifacts, [artifact])
self.assertEqual(context.to_dict()["inherited_task_artifacts"][0]["task_id"], "task-2")
```

Mutate the caller-provided artifact list after `build()` and prove the context list length is unchanged.

Build a simple context without a plan and assert `inherited_task_artifacts == []` and the serialized dictionary omits the key.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_context_builder
```

- [ ] **Step 3: Implement minimal plumbing**

Append this optional argument to `ContextBuilder.build`:

```python
inherited_task_artifacts: list[TaskArtifact] | None = None
```

Pass a copied list to `AgentContext`. Do not load artifacts from run memory, workspace config, global Observations, or files. The Agent Loop is the only source.

- [ ] **Step 4: Run focused tests and verify GREEN**

Expected: PASS with existing V0.6 and V0.8 context tests unchanged.

## Task 4: Integrate artifacts and isolation into the Agent Loop

**Files:**

- Modify: `src/min_agent/agent_loop.py`
- Modify: `tests/test_agent_loop.py`
- Modify: `tests/test_permission_flow.py`

- [ ] **Step 1: Update scripted test actions**

Every successful planned `complete_task` in tests must include a named `TaskArtifactDraft`. Keep simple-mode actions unchanged.

- [ ] **Step 2: Write a failing successful-plan test**

Use a scripted two-task plan with a minimal scripted decision model; do not instantiate `FakeLLM` in this Task 4 test, because its legacy hidden fields are intentionally removed and integration-tested in Task 5. Assert:

- the first task context has `inherited_task_artifacts=[]`;
- the second task context has the first available artifact;
- task-1 Observations are absent from task-2 `working observations`;
- task-1 selected project content is absent from task-2 selected project content;
- each `task_artifact_created` immediately precedes its matching `task_completed`;
- artifact `created_at_step` equals the `task_artifact_created` TraceEvent step;
- `evidence_observations` contains only the cited current-task Observation summaries;
- final planned context has `inherited_task_artifacts` containing both available artifacts in plan order, `observations == []`, `selected_project_content == []`, and `current_task_id is None`;
- run completes only after every task has an available artifact.

Expected phase subsequence:

```python
[
    "plan_created",
    "task_started",
    "task_artifact_created",
    "task_completed",
    "task_started",
    "task_artifact_created",
    "task_completed",
    "final_answer",
    "run_completed",
]
```

- [ ] **Step 3: Write failing invalid-artifact tests**

Test missing draft, blank title, blank content, invalid evidence, and wrong task ID. Each case must produce:

```text
task_failed(current)
-> task_artifact_missing(current)
-> task_skipped(each pending)
-> task_artifact_missing(each skipped)
-> final_answer(failed)
-> run_failed
```

Assert there is no `task_artifact_created` for failed or skipped tasks and no later task tool call.

- [ ] **Step 4: Write failing permission-rejection tests**

For a denied `run_command` or `write_file` in a planned task, assert:

- `permission_resolved.output.approved is False`;
- no corresponding `tool_started` occurs;
- the rejected Observation cannot create an available artifact;
- the failed task's missing event includes artifacts inherited before it started;
- skipped tasks have empty `inherited_task_ids` and their skip reason;
- existing simple-mode rejection behavior remains unchanged.

- [ ] **Step 5: Run focused tests and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_agent_loop tests.test_permission_flow
```

- [ ] **Step 6: Implement per-task dynamic context isolation**

Keep the existing global `self.observations` for simple-mode compatibility and run-level diagnostics. Add:

```python
self._task_selected_project_content: list[str] = []
```

Change `_clear_task_buffer()` to clear both current-task Observations and current-task selected content. In planned mode, Context Build receives those two task-local lists. In simple mode, it continues to receive global Observations and existing global selected content.

When a successful `read_file` result arrives, append the path label to the current-task selected-content list in planned mode and to the existing global list in simple mode. Do not append a planned read path to the simple/global model-facing selected-content list. `ContextLoader` is not part of this path and must not be changed: in V0.6 it loads run-level base context, while `AgentLoop` owns the dynamic selected-path lists. The file body remains in the successful current-task `Observation.result.content`; selected project content remains path labels and is passed through `ContextBuilder` without another file read.

A successful `list_dir` result remains only in the current task's Working Observations. It never enters `selected_project_content`: task-1 may complete from its directory-list Observation, but its selected project content stays empty.

Pass `self.task_plan.artifacts()` to `ContextBuilder` as inherited artifacts. This list contains only available completed artifacts.

Set `task_id=self._current_task_id()` on planned `context_built` and `llm_decision` events so every model round is explicitly task-scoped. The final all-artifacts Context Build has `task_id=None` because no task is running.

- [ ] **Step 7: Implement successful artifact emission**

In `_handle_complete_task`:

1. Read `artifact_step = self.recorder.next_step()`.
2. Call `TaskPlan.complete_current(..., task_artifact=action.task_artifact, created_at_step=artifact_step)`.
3. Emit `task_artifact_created` immediately and assert through tests that its returned step matches `created_at_step`.
4. Emit `task_completed`.
5. Clear task-local Observations and selected project content immediately, including after the final task.
6. Only then check `all_completed()` or emit `task_started` for the next task.

Build `evidence_observations` only from the cited indexes and include `index`, `tool_name`, copied `args`, and `success`. Derive `inherited_task_ids` from artifacts preceding the current one and `forwarded_task_ids` from later task definitions.

- [ ] **Step 8: Implement missing artifact emission**

Before failing the current task, capture its ID and the available artifact IDs that were inherited when it ran. After `fail_current()`:

- emit `task_failed`, then `task_artifact_missing` for the failed task;
- for each skipped task, emit `task_skipped`, then `task_artifact_missing`;
- construct missing payloads with blank content/indexes, `status="missing"`, the event's next step, and the exact failure or skip reason;
- never insert missing artifacts into `TaskPlan.artifacts()`.

Add both phases to `_emit_task_event` titles/status mapping or use focused artifact emitters. Do not suppress `TaskPlanError` silently in new code; if failure handling itself cannot transition the plan, emit a deterministic `run_failed` reason that exposes the local state error without crashing.

- [ ] **Step 9: Make the final planned answer artifact-backed**

The final model decision receives all available artifacts in `inherited_task_artifacts`. The Agent Loop still accepts the model's final message. Assert in the two-task test that the final Context Build contains exactly the two available artifacts, `observations == []`, `selected_project_content == []`, and `current_task_id is None`; assert the canonical four-task scenario likewise contains all four available artifacts in plan order. No prior raw Observation may be required for the final model decision.

- [ ] **Step 10: Run focused tests and verify GREEN**

Run the Step 5 command. Expected: PASS.

## Task 5: Remove FakeLLM hidden cross-task state

**Files:**

- Modify: `src/min_agent/fake_llm.py`
- Modify: `tests/test_fake_llm.py`

- [ ] **Step 1: Write failing no-hidden-state tests**

Assert a new `FakeLLM` instance has neither `_composite_read_contents` nor `_composite_time_result`.

Build task contexts directly and prove behavior depends only on public context:

- task-2 chooses Markdown files from task-1's inherited file-list artifact;
- task-3 copies the successful command Observation content into its draft artifact;
- task-4 builds `write_file.content` from task-2 summary and task-3 time artifacts;
- changing inherited artifact content changes the task-4 write content;
- task-4 with missing task-2 or task-3 artifact returns a failed final action rather than inventing content;
- final action after all tasks uses artifact-backed completion information.

- [ ] **Step 2: Write exact artifact assertions**

```python
self.assertEqual(action.kind, "complete_task")
self.assertEqual(action.task_artifact.title, "当前本地时间")
self.assertEqual(action.task_artifact.content, "2026-07-10 16:45:21 CST")
self.assertEqual(action.evidence_observation_indexes, [1])
```

For task-2, assert artifact content is synthesized only from successful current-task `read_file` Observations. For task-4, assert its own artifact describes the successful write result and cites only the write Observation.

Add an `AgentLoop + FakeLLM` integration test after the hidden fields are removed. Run a two-task artifact-backed plan and assert the `FakeLLM` instance has neither legacy field, the loop reaches its final answer through inherited artifacts, and no cross-task data is read from private state.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_fake_llm
```

- [ ] **Step 4: Implement artifact-driven FakeLLM logic**

Delete the two hidden fields and all writes/reads to them. Add pure helpers that receive `AgentContext`, for example:

```python
def _inherited_artifact(self, context: AgentContext, task_id: str) -> TaskArtifact | None:
    return next(
        (artifact for artifact in context.inherited_task_artifacts
         if artifact.task_id == task_id and artifact.status == "available"),
        None,
    )
```

Task behavior:

- task-1 completes with the successful `list_dir` content as a file-list draft.
- task-2 parses task-1 artifact lines, selects up to `MAX_FAKE_READS` relevant `.md` files, excludes `summary.md` and `minagent.md`, reads them, and creates a concise summary from the successful current-task read Observations.
- task-3 creates a time draft by copying the successful command Observation content.
- task-4 requires task-2 and task-3 available artifacts, builds file content from them, requests `write_file`, then creates a write-result draft from the successful current-task write Observation.
- after all tasks complete, final output states that `summary.md` was created and is based on stored artifacts.

Do not read `self.observations`, run records, workspace files, or class state as a cross-task fallback.

- [ ] **Step 5: Run focused tests and verify GREEN**

Expected: PASS.

## Task 6: Make DeepSeek produce and consume explicit artifacts

**Files:**

- Modify: `src/min_agent/deepseek_llm.py`
- Modify: `tests/test_deepseek_llm.py`

- [ ] **Step 1: Write failing parser tests**

Valid input includes a nested object:

```json
{"kind":"complete_task","task_id":"task-1","completion_evidence":"Observation 1 succeeded","evidence_observation_indexes":[1],"task_artifact":{"title":"Workspace Markdown 文件清单","content":"project.md"},"reason":"criterion met"}
```

Assert parsing produces `TaskArtifactDraft` with trimmed title/content and preserves model-call metadata.

Reject each case as a failed `final_answer` action:

- missing `task_artifact`;
- non-object `task_artifact`;
- missing, non-string, or blank `title`;
- missing, non-string, or blank `content`;
- model-supplied runtime fields such as `status`, `created_at_step`, or `task_id` inside the nested object.

Keep existing evidence-index type validation, including boolean rejection.

- [ ] **Step 2: Write failing prompt tests**

Assert the system prompt states:

- `working_observations` are current-task-only and are the only completion evidence source;
- `selected_project_content` is current-task-only;
- `inherited_task_artifacts` contains prior stable outputs and cannot be cited as evidence;
- `complete_task` requires non-empty `task_artifact.title` and `task_artifact.content`;
- final planned answers use inherited stored artifacts;
- no hidden state or previous raw Observation may substitute for artifacts.

Assert the user prompt has three separate keys in planned mode:

```text
working_observations
selected_project_content
inherited_task_artifacts
```

Assert a simple context omits `inherited_task_artifacts` and retains the existing output contract.

Add a completed-plan prompt test where every task is `completed` and `current_task_id is None`. It must instruct DeepSeek to return `final_answer` based on stored artifacts, not to act on a nonexistent current task or return another `create_plan`.

- [ ] **Step 3: Run focused tests and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_deepseek_llm
```

- [ ] **Step 4: Implement strict parsing**

In `_parse_complete_task`, validate the nested object and allow exactly `title` and `content`. Construct:

```python
TaskArtifactDraft(title=title.strip(), content=content.strip())
```

Pass it as the named `task_artifact` argument to `AgentAction.complete_task`.

- [ ] **Step 5: Update prompts and examples**

Update V0.8 labels to V0.9 where they describe artifact behavior. Keep tool, permission, path, and command restrictions unchanged. The prompt must not promise semantic evidence validation that the runtime does not implement.

In `_user_prompt`, serialize inherited artifacts only for a planned context. Keep all three dynamic sources separate; do not concatenate artifacts into observations or selected content.

Inside the existing `prompt_parts["task_instruction"]` assignment in `_user_prompt`, split the planned instruction by state:

- when `current_task_id` is present, act only on that task and use only current-task Observation indexes as evidence;
- when every task is completed and `current_task_id` is `None`, return `final_answer` based on the inherited stored artifacts;
- never return a second `create_plan` in either state.

- [ ] **Step 6: Run focused tests and verify GREEN**

Expected: PASS.

## Task 7: Add artifact details inside the task-plan panel only

**Files:**

- Modify: `web/trace_viewer.html`
- Modify: `web/trace_viewer.js`
- Modify: `web/trace_viewer.css`
- Modify: `tests/test_trace_viewer_source.py`

- [ ] **Step 1: Write failing DOM boundary tests**

Assert the unchanged top-level order:

```python
status_pos = html.index('class="status"')
request_pos = html.index('id="original-request"')
summary_pos = html.index('class="summary-panel"')
result_pos = html.index('id="final-answer"')
plan_pos = html.index('id="task-plan-panel"')
layout_pos = html.index('class="layout"')
self.assertEqual(
    sorted([status_pos, request_pos, summary_pos, result_pos, plan_pos, layout_pos]),
    [status_pos, request_pos, summary_pos, result_pos, plan_pos, layout_pos],
)
```

Extract the `#task-plan-panel` section and assert these IDs are inside it:

```text
task-artifact-panel
task-artifact-title
task-artifact-status
task-artifact-body
```

Assert those IDs occur before the panel's closing `</section>` and before `.layout`. Assert `#selected-task-label` remains between the rounds-panel opening and `#round-list`; do not move it.

Assert no new top-level `<section>` exists between the task-plan panel and `.layout`, and no artifact control contains form, input, edit, approve, reject, retry, or execute behavior.

- [ ] **Step 2: Write failing JavaScript structure tests**

Require focused functions:

```text
buildTaskArtifacts
artifactForTask
renderSelectedTaskArtifact
formatArtifactEvidence
```

Assert `renderTaskPlan()` invokes `renderSelectedTaskArtifact()` after task selection is resolved. Assert no artifact renderer writes to `#round-detail`, `#round-list`, `#run-summary`, `#original-request`, `#final-answer`, or status elements.

Require both artifact phases in `moduleForPhase` so existing round-detail generic rendering can label them without structural changes.

- [ ] **Step 3: Run source tests and verify RED**

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_trace_viewer_source
```

- [ ] **Step 4: Add only the allowed HTML**

Inside `#task-plan-panel`, after `#task-list`, add:

```html
<section id="task-artifact-panel" class="task-artifact-panel" aria-live="polite">
  <div class="task-artifact-heading">
    <div>
      <h3 id="task-artifact-title">所选任务产物</h3>
      <p>查看主产物、当前任务证据、继承来源和后续流向。</p>
    </div>
    <span id="task-artifact-status" class="task-artifact-status">waiting</span>
  </div>
  <div id="task-artifact-body" class="task-artifact-body"></div>
</section>
```

Do not change any markup outside the existing task-plan section.

- [ ] **Step 5: Derive artifact state only from Trace events**

`buildTaskArtifacts(events)` scans `task_artifact_created` and `task_artifact_missing`. For each task ID, retain the latest valid event and expose its artifact, evidence summaries, inherited IDs, and forwarded IDs. It must not infer artifact content from tool output, model-call raw JSON, task title, or final answer.

`buildTaskPlan(events)` continues to derive task definitions/statuses as V0.8 does and attaches artifact lookup results without changing round filtering.

- [ ] **Step 6: Render selected-task artifact states**

`renderSelectedTaskArtifact(plan)` handles:

- pending/running with no event: `waiting`, “本任务尚未产生产物”；
- available: primary content, evidence list, inherited chips, forwarded chips;
- missing: `missing`, exact failure/skip reason and inherited context if present;
- no selected task or simple mode: clear body while the entire parent panel remains hidden through existing logic.

Use DOM APIs and `textContent` for event-derived strings. Do not inject unescaped trace content with `innerHTML`.

When a task card is clicked, keep existing round filtering and also refresh the artifact area. Auto-selection behavior remains unchanged.

- [ ] **Step 7: Add scoped CSS from the prototype**

Add only selectors rooted at `.task-plan-panel`, `.task-artifact-panel`, or their descendants. Reproduce the prototype's two-column content/evidence layout, artifact flow blocks, available/missing states, and chips while adapting to existing CSS variables.

Add artifact-scoped responsive rules that match the checked-in V0.9 prototype: at `max-width: 1050px`, switch the artifact grid to one column; at `max-width: 760px`, switch the artifact flow to one column. Keep the existing page-wide `800px` breakpoint unchanged. Ensure `pre` content wraps with:

```css
white-space: pre-wrap;
overflow-wrap: anywhere;
min-width: 0;
```

Do not alter colors, dimensions, typography, spacing, or responsive behavior of modules outside the task-plan panel.

- [ ] **Step 8: Run source tests and verify GREEN**

Run the Step 3 command, then run the FakeLLM and AgentLoop tests together to protect the canonical integration boundary:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest tests.test_fake_llm tests.test_agent_loop
```

Expected: PASS.

- [ ] **Step 9: Review the page boundary diff**

```bash
git diff -- web/trace_viewer.html web/trace_viewer.js web/trace_viewer.css tests/test_trace_viewer_source.py
```

Reject the implementation if HTML outside `#task-plan-panel` changed, except adding the two new phase labels to existing JavaScript event maps.

## Task 8: Add complete CLI scenarios and perform real browser acceptance

**Files:**

- Modify: `tests/test_cli_scenarios.py`
- Modify: `tests/test_project_testing_rules.py` only if required by the new AGENTS section
- Runtime artifacts only in a temporary workspace and `runs/`

- [ ] **Step 1: Write the successful FakeLLM CLI scenario**

Use `tempfile.TemporaryDirectory()` inside the test, create the project Markdown fixtures there, approve both dangerous tools through the existing test callback/input mechanism, and run the full canonical goal.

Assert the saved run record contains four available artifact events in task order. For task-4 Context Build, assert task-2 summary and task-3 time are present under `inherited_task_artifacts`. Assert task-1/task-2 raw Observations are absent from task-4 `observations` and task-4 `selected_project_content` is empty before writing.

Read the generated `summary.md` and assert it contains text from task-2's stored artifact and the exact task-3 time artifact. Do not assert against FakeLLM private fields.

- [ ] **Step 2: Write the rejection scenario**

Deny the task-3 command permission. Assert:

- task-1 and task-2 each have `task_artifact_created`;
- task-3 has `task_failed` and `task_artifact_missing`;
- task-4 has `task_skipped` and `task_artifact_missing`;
- no task-3 command `tool_started` occurs;
- no task-4 `write_file` permission or tool event occurs;
- `summary.md` does not exist.

- [ ] **Step 3: Write the simple-goal regression scenario**

Run `现在几点？` and assert no `plan_created`, task lifecycle, artifact phase, or `inherited_task_artifacts` output exists. Existing permission and command safety assertions remain.

- [ ] **Step 4: Run the complete automated suite**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

Expected: all tests pass with no skipped V0.9 tests and no new dependency.

- [ ] **Step 5: Prepare a real browser run without polluting the example workspace**

Create a temporary workspace, copy only required Markdown fixtures, and run the canonical goal with the existing Trace Server/Viewer flow. Use the current CLI instructions from `docs/runbook.md`; do not invent a new server command or bypass CLI permissions.

Keep generated runs and `summary.md` until acceptance is complete. Do not delete them without user authorization.

- [ ] **Step 6: Browser acceptance matrix**

Verify in a real browser or equivalent browser runtime:

| Mode | Required check |
| --- | --- |
| Success | page is nonblank; four task cards render; clicking each card changes artifact content, evidence, inheritance, and flow |
| Failure | failed task shows missing reason; skipped task explains it never ran; no available artifact is shown |
| Simple | whole task-plan panel remains hidden |
| Desktop | existing module order and round/detail interactions are unchanged |
| Narrow screen | task cards and artifact content remain readable with no horizontal overflow |
| Console | no JavaScript error or unhandled promise rejection |

Also compare the status, original request, summary, final result, rounds, selected-task label, and round-detail modules against V0.8. Any visual or interaction change outside the task-plan module is a release blocker.

Record one of these exact outcomes in `docs/runbook.md`:

```text
browser manual smoke: PASS
```

or, if no real browser was used:

```text
browser manual smoke: NOT RUN - <concrete reason>
```

Source tests alone never justify `PASS`.

- [ ] **Step 7: Report generated artifacts**

List temporary workspace path, generated `summary.md`, run record paths, screenshots, and logs. State which should be retained. Ask before deleting any file or directory.

## Task 9: Finish user documentation and run final verification

**Files:**

- Modify: `README.md`
- Modify: `docs/runbook.md`
- Modify: `CHANGELOG.md`
- Review: every file in this plan

- [ ] **Step 1: Update README behavior and boundaries**

Document:

- V0.9 adds one stored artifact per completed planned task;
- prior artifacts are separate from current-task Observations;
- FakeLLM and DeepSeek use the same public artifact contract;
- the canonical composite command and its two permission prompts;
- simple goals and all existing safety boundaries remain unchanged;
- Viewer changes exist only inside the task-plan module.

- [ ] **Step 2: Update the runbook with exact evidence**

Include the successful event chain, rejection event chain, test command/result, browser outcome, generated artifact paths, and cleanup status. Do not claim a DeepSeek live run unless a real API-backed run was performed with user-provided environment credentials.

- [ ] **Step 3: Update CHANGELOG without overwriting existing edits**

Inspect `git diff -- CHANGELOG.md` again. Add a top-level implemented `V0.9` entry explaining the user-visible problem, behavior, exclusions, and completion criteria. Preserve the existing V1.0 and later roadmap text. Do not convert the changelog into a commit/file list.

- [ ] **Step 4: Run requirement coverage checks**

```bash
rg -n "TaskArtifact|task_artifact_created|task_artifact_missing|inherited_task_artifacts" src tests web README.md docs/runbook.md CHANGELOG.md
rg -n "_composite_read_contents|_composite_time_result" src tests
rg -n "task-artifact-panel|task-artifact-title|task-artifact-status|task-artifact-body" web tests
```

Expected:

- artifact contracts appear in runtime, tests, and docs;
- hidden FakeLLM fields return no matches;
- all artifact DOM IDs are inside `#task-plan-panel` and covered by tests.

- [ ] **Step 5: Run diff integrity checks**

```bash
git diff --check
git status -sb
git diff --stat
```

Inspect every changed file. Confirm there is no `.env`, secret, generated `summary.md`, browser cache, screenshot, run record, dependency lockfile, CI file, or unrelated refactor in the intended change set. Do not delete unexpected files; report them.

- [ ] **Step 6: Run final automated verification**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

Expected: PASS. Record the exact test count and duration from the fresh run.

- [ ] **Step 7: Final implementation report**

Report:

- files changed and why;
- exact automated test result;
- browser smoke result;
- canonical success and rejection event evidence;
- whether a live DeepSeek run was performed;
- generated artifact/cleanup status;
- confirmation that page changes were limited to `#task-plan-panel`;
- remaining limitations from the V0.9 product document.

Do not commit, push, merge, tag, delete, or clean anything. Wait for separate user authorization.

## 5. Test and acceptance matrix

| Layer | Main files | Required proof |
| --- | --- | --- |
| Data contract | `test_types.py`, `test_trace_recorder.py` | nested draft/runtime artifact serialization, phases, exact step |
| State machine | `test_task_plan.py` | atomic completion+artifact, current-task evidence, no artifacts on failure/skip |
| Context | `test_context_builder.py`, `test_agent_loop.py` | three dynamic sources separated; no prior raw Observation/content leakage |
| FakeLLM | `test_fake_llm.py` | no hidden fields; task-4 output changes with inherited artifacts |
| DeepSeek | `test_deepseek_llm.py` | strict nested parser and explicit inheritance/evidence prompts |
| Permissions | `test_permission_flow.py`, `test_agent_loop.py` | denial creates missing artifacts and never starts the tool |
| CLI scenarios | `test_cli_scenarios.py` | real run-record chain and artifact-backed `summary.md` |
| Viewer source | `test_trace_viewer_source.py` | artifact UI inside task plan; all other DOM/module boundaries frozen |
| Browser | manual/equivalent browser | nonblank, clickable task/artifact switching, failure/simple modes, narrow screen, clean console |
| Full regression | `unittest discover` | every V0.1-V0.8 mechanism remains green |

## 6. Explicit non-goals and rejection conditions

Reject the implementation if any of these occurs:

- artifact content is copied from a global cache, previous raw Observation list, final answer, or reconstructed Viewer state;
- a completed task has no available artifact;
- a failed or skipped task has an available artifact;
- inherited artifact IDs are accepted as completion evidence indexes;
- DeepSeek can omit artifact content and still complete a task;
- task-4 writes a summary without task-2 and task-3 available artifacts;
- a denied dangerous tool emits `tool_started`;
- the Viewer obtains artifact data from anything other than Trace events;
- artifact UI is added beside the task-plan panel, inside the round-detail panel, or as a new top-level page section;
- any page module outside `#task-plan-panel` is moved, redesigned, renamed, or given new controls;
- simple goals show plan or artifact UI/events;
- implementation adds dynamic planning, retry, recovery, parallel tasks, dependencies, nested tasks, long-term memory, multi-Agent, MCP, Hook, plugins, arbitrary commands, web approvals, or page task submission;
- tests pass only because an assertion was weakened, an error was swallowed, or an existing test was removed;
- browser acceptance is reported as PASS without a real browser/equivalent runtime check.

## 7. Completion definition

V0.9 is complete only when all of the following are true:

1. Each completed task in a composite run has one stored, observable available artifact.
2. Artifact evidence references only successful current-task Observations.
3. Later tasks receive prior available artifacts through `inherited_task_artifacts` and no private side channel.
4. Previous raw Observations and selected project content do not leak into later task working context.
5. FakeLLM has no hidden cross-task state.
6. DeepSeek parser and prompts enforce the same artifact contract.
7. Failure and skip paths produce explicit missing-artifact events and no available artifacts.
8. Final composite output is based on stored artifacts.
9. Viewer artifact content, evidence, inheritance, and flow switch with the selected task.
10. Every page change is confined to `#task-plan-panel`; all other page areas remain unchanged.
11. Simple-goal behavior remains V0.7-compatible.
12. Full automated tests pass and browser acceptance is honestly recorded.
