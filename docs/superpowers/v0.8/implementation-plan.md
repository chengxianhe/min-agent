# min-agent-demo V0.8 Observable Task Planning Implementation Plan

> **For agentic workers:** Execute this plan task by task with test-first changes and review checkpoints. Do not use subagents. Do not merge tasks, skip RED/GREEN verification, or commit without separate user authorization.

**Goal:** Add observable 2–5 task planning and sequential execution for composite goals while preserving the V0.7 execution path and Trace Viewer structure for simple goals.

**Architecture:** Extend the existing `AgentAction` contract with `create_plan` and `complete_task`, keep all tool calls inside the existing `AgentLoop` and `ToolRegistry`, and put task transition invariants in a focused local `TaskPlan` state machine. Every task-scoped trace event carries a stable `task_id`; the Viewer derives the plan and task-filtered Agentic Loop rounds only from trace events. A model may propose that a task is complete, but it must cite concrete current-task Observation indexes; the state machine accepts completion only when every cited Observation belongs to the current task and succeeded.

**Tech Stack:** Python standard library (`dataclasses`, `typing`, `unittest`), existing FakeLLM and DeepSeek JSON decision adapters, existing `TraceRecorder`/SSE server, vanilla HTML/CSS/JavaScript Trace Viewer.

---

## 1. Frozen inputs and executor contract

Read these files completely before changing implementation:

```text
AGENTS.md
docs/superpowers/v0.8/product-design.md
docs/superpowers/v0.8/trace-viewer-prototype.html
docs/superpowers/v0.8/implementation-plan.md
```

The product design and prototype are frozen. If their hashes no longer match the collaboration record, stop instead of adapting the implementation to changed inputs.

Hard constraints:

- Simple goals must continue through the V0.7 `tool_call -> Observation -> final_answer` path and must not produce plan or task events.
- A plan contains 2–5 fixed tasks. Task count, order, `task_id`, title, and completion criteria cannot change after `plan_created`.
- A task is a verifiable subgoal, not a tool call. One task may contain multiple model rounds and multiple tool calls.
- The model proposes `create_plan` and `complete_task`; only local validation and the `TaskPlan` state machine change task status.
- `AgentLoop` remains tool-agnostic and must call tools only through `ToolRegistry`.
- V0.8 validates structural completion evidence: the model must cite real, successful Observations from the current task, and local code verifies those indexes and results. V0.8 does not implement semantic matching between free-text `completion_criteria` and arbitrary tool output content; choosing relevant evidence remains the decision model's responsibility and is constrained by scenario tests.
- Existing `write_file` and `run_command` validation and CLI permission chains remain unchanged.
- In a composite run, the first tool error, permission rejection, failed model action, invalid completion claim, or max-turn exhaustion fails the current task, skips all pending tasks, and stops the run.
- No `tool_started` event may appear after a denied permission for that tool.
- Trace Viewer remains read-only. Do not add approve, reject, edit, reorder, retry, resume, or execute controls.
- Preserve all seven V0.6 Context Build source cards and all V0.7 command details.
- Do not install dependencies, read or create `.env`, use a real API key in tests, or loosen workspace/command boundaries.
- Do not commit, push, merge, tag, delete, or clean files without separate user authorization.

## 2. Final user-visible effect

Running the FakeLLM scenario:

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。" \
  --workspace examples/workspace
```

must produce this semantic event path before completion:

```text
run_started
-> context_built
-> llm_decision(create_plan)
-> plan_created(4 pending tasks)
-> task_started(task-1)
-> list_dir / observation_added
-> llm_decision(complete_task task-1)
-> task_completed(task-1)
-> task_started(task-2)
-> one or more read_file / observation_added
-> task_completed(task-2)
-> task_started(task-3)
-> permission_requested(run_command)
-> permission_resolved(approved=true)
-> tool_started(run_command, task_id=task-3)
-> observation_added
-> task_completed(task-3)
-> task_started(task-4)
-> permission_requested(write_file)
-> permission_resolved(approved=true)
-> tool_started(write_file, task_id=task-4)
-> observation_added
-> task_completed(task-4)
-> final_answer
-> run_completed
```

The Viewer module order must be:

```text
运行状态
-> 本次任务统计
-> 原始需求
-> 最终结果
-> 任务计划（only for 2–5 task plans）
-> 执行轮次 / 轮次详情
```

Clicking a task card filters the left column to that task's rounds. Clicking a round still renders the original Context, Model, Permission, Tool, Observation, and raw-event details in the right column.

For `现在几点？`, the event path and page remain V0.7: no `plan_created`, no task lifecycle events, no visible task plan panel, and no selected-task label.

## 3. File responsibility map

### Create

- `src/min_agent/task_plan.py`: validate immutable plan definitions and own all legal task status transitions.
- `tests/test_task_plan.py`: task-count, identity, ordering, completion-evidence, single-running-task, failure, and skip invariants.

### Modify

- `src/min_agent/types.py`: task types, new action kinds, task-scoped context, task-aware trace events.
- `src/min_agent/context_builder.py`: copy the current task plan snapshot into every model context.
- `src/min_agent/agent_loop.py`: accept plan actions, emit lifecycle events, scope events to tasks, and stop composite runs on first failure.
- `src/min_agent/fake_llm.py`: deterministic V0.8 composite demo while preserving all simple-goal routes.
- `src/min_agent/deepseek_llm.py`: strict JSON parsing and prompts for plan creation/completion.
- `src/min_agent/cli.py`: allow enough loop turns for the four-task scenario; no new permission UI.
- `web/trace_viewer.html`: insert the conditional plan panel and selected-task label in the frozen module order.
- `web/trace_viewer.js`: derive task state, filter rounds, render lifecycle details, and preserve V0.7 rendering.
- `web/trace_viewer.css`: task-plan states and responsive layout copied from the frozen prototype.
- `tests/test_types.py`, `tests/test_context_builder.py`, `tests/test_agent_loop.py`, `tests/test_fake_llm.py`, `tests/test_deepseek_llm.py`, `tests/test_cli.py`, `tests/test_cli_scenarios.py`, `tests/test_trace_viewer_source.py`: V0.8 coverage and V0.7 regression protection.
- `README.md`, `docs/runbook.md`, `CHANGELOG.md`: user scenario, boundaries, event chain, browser acceptance, and completion criteria.

No schema migration, dependency change, `.env`, CI/CD, database, global configuration, or public release file is required.

## Task 1: Add task and action data contracts

**Files:**

- Modify: `src/min_agent/types.py`
- Modify: `tests/test_types.py`

- [ ] **Step 1: Write failing serialization tests**

Add tests that require these public contracts:

```python
task = TaskDefinition(
    task_id="task-1",
    title="查看项目文件",
    completion_criteria="成功获得 workspace 根目录文件列表。",
)
action = AgentAction.create_plan([task], reason="Need an explicit plan")
self.assertEqual(action.kind, "create_plan")
self.assertEqual(action.to_dict()["tasks"][0]["task_id"], "task-1")

completion = AgentAction.complete_task(
    task_id="task-1",
    completion_evidence="list_dir Observation succeeded",
    evidence_observation_indexes=[1],
    reason="The criterion is satisfied",
)
self.assertEqual(completion.kind, "complete_task")
self.assertEqual(completion.task_id, "task-1")
self.assertEqual(completion.evidence_observation_indexes, [1])

event = TraceEvent(
    run_id="run-1",
    step=1,
    timestamp="2026-07-07T00:00:00+08:00",
    phase="task_started",
    status="running",
    title="开始任务",
    task_id="task-1",
)
self.assertEqual(event.to_dict()["task_id"], "task-1")
```

Also assert that an ordinary V0.7 `tool_call` serializes with `tasks=[]`, `task_id=None`, and `completion_evidence=None`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_types
```

Expected: FAIL because the task types and action factories do not exist.

- [ ] **Step 3: Implement the contracts**

Add these exact concepts without changing existing field meanings:

```python
TaskStatus = Literal["pending", "running", "completed", "failed", "skipped"]
ActionKind = Literal["create_plan", "complete_task", "tool_call", "final_answer"]

@dataclass(frozen=True)
class TaskDefinition:
    task_id: str
    title: str
    completion_criteria: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass(frozen=True)
class TaskSnapshot:
    task_id: str
    title: str
    completion_criteria: str
    status: TaskStatus
    failure_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

Extend `EventPhase` with:

```python
"plan_created",
"task_started",
"task_completed",
"task_failed",
"task_skipped",
```

Extend `AgentAction` with defaults that do not disturb existing constructors:

```python
tasks: list[TaskDefinition] = field(default_factory=list)
task_id: str | None = None
completion_evidence: str | None = None
evidence_observation_indexes: list[int] = field(default_factory=list)
```

Add `create_plan` and `complete_task` class methods with the arguments exercised by the tests above. Make `AgentAction.to_dict()` explicitly serialize `tasks` through `TaskDefinition.to_dict()` and copy the evidence-index list rather than relying on nested `asdict` behavior.

Extend `AgentContext` with:

```python
task_plan: list[TaskSnapshot] = field(default_factory=list)
current_task_id: str | None = None
```

Only include `task_plan` and `current_task_id` in `AgentContext.to_dict()` when a plan exists. Extend `TraceEvent` with `task_id: str | None = None`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the same command. Expected: all `tests.test_types` tests pass.

- [ ] **Step 5: Inspect without committing**

Run `git diff -- src/min_agent/types.py tests/test_types.py`. Do not commit.

## Task 2: Implement the local task-plan state machine

**Files:**

- Create: `src/min_agent/task_plan.py`
- Create: `tests/test_task_plan.py`

- [ ] **Step 1: Write failing state-machine tests**

Cover all of these cases with explicit assertions:

```python
definitions = [
    TaskDefinition("task-1", "查看文件", "获得成功的目录 Observation"),
    TaskDefinition("task-2", "读取资料", "获得成功的读取 Observation"),
]
plan = TaskPlan.create(definitions)
self.assertEqual([item.status for item in plan.snapshot()], ["pending", "pending"])

started = plan.start_next()
self.assertEqual(started.task_id, "task-1")
self.assertEqual([item.status for item in plan.snapshot()], ["running", "pending"])

with self.assertRaises(TaskPlanError):
    plan.complete_current("task-1", "", [], observations=[])

observations = [Observation("list_dir", {"path": "."}, ToolResult(success=True))]
completed = plan.complete_current(
    "task-1",
    "The directory listing succeeded",
    [1],
    observations,
)
self.assertEqual(completed.status, "completed")
```

Additional tests must reject 0, 1, and 6 tasks; duplicate/non-sequential IDs; blank titles; blank completion criteria; completing the wrong task; blank evidence text; empty, duplicate, boolean, zero, negative, out-of-range, or missing current-task Observation indexes; cited failed Observations; starting a second task while one is running; mutating a returned `TaskSnapshot` and verifying the next `snapshot()` is unchanged; and modifying the caller's original task list after plan creation.

Also add one explicit boundary test proving V0.8's structural-evidence scope: if the completion criterion text says `生成 summary.md` but the cited current-task Observation is a successful `list_dir`, `TaskPlan.complete_current()` accepts it because semantic relevance is outside the state machine. This test documents the limitation; scenario tests must still ensure FakeLLM and DeepSeek prompts cite relevant Observations for the frozen demo path.

Failure tests must assert:

```python
failed, skipped = plan.fail_current("permission denied by user")
self.assertEqual(failed.status, "failed")
self.assertEqual(skipped[0].status, "skipped")
self.assertIn("task-1", skipped[0].failure_reason)
self.assertIsNone(plan.current_task())
```

- [ ] **Step 2: Run the focused test and verify RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_task_plan
```

Expected: FAIL because `min_agent.task_plan` does not exist.

- [ ] **Step 3: Implement `TaskPlan`**

Use a private mutable runtime record and expose only copies as `TaskSnapshot`. The public API consists of `TaskPlan.create(definitions)`, `snapshot()`, `current_task()`, `start_next()`, `complete_current(task_id, completion_evidence, evidence_observation_indexes, observations)`, `fail_current(reason)`, and `all_completed()`. Return types are respectively `TaskPlan`, `list[TaskSnapshot]`, `TaskSnapshot | None`, `TaskSnapshot | None`, `TaskSnapshot`, `tuple[TaskSnapshot, list[TaskSnapshot]]`, and `bool`. Invalid input or transitions raise `TaskPlanError(ValueError)`.

Validation rules are exact:

- length is 2–5;
- IDs equal the sequential values `task-1` through `task-N` in list order;
- IDs are unique;
- stripped title and completion criteria are non-empty;
- definitions are copied at creation;
- only one runtime record may be `running`;
- `start_next()` starts the next pending task and does not accept global Observation counts;
- `complete_current()` requires the current ID, non-empty evidence text, and at least one explicitly cited 1-based Observation index from the current task's Observation list; every index must be unique, in range for the passed current-task list, and have `result.success is True`;
- `fail_current()` fails the running task and changes every pending task to `skipped` with `前序任务 <id> 失败，未执行：<reason>`;
- completed/failed/skipped states are terminal.

- [ ] **Step 4: Run focused tests and verify GREEN**

Expected: all task-plan tests pass.

- [ ] **Step 5: Run type and state-machine tests together**

```bash
PYTHONPATH=src python3 -m unittest tests.test_types tests.test_task_plan
```

Expected: PASS.

## Task 3: Put task state into Context and Trace

**Files:**

- Modify: `src/min_agent/context_builder.py`
- Modify: `src/min_agent/trace_recorder.py`
- Modify: `tests/test_context_builder.py`
- Modify: `tests/test_trace_recorder.py`

- [ ] **Step 1: Write failing tests**

Require `ContextBuilder.build` to accept:

```python
task_plan=[TaskSnapshot("task-1", "查看文件", "目录成功", "running")],
current_task_id="task-1",
```

Assert that both values appear in the returned context and serialized context. Build once without those arguments and assert `task_plan == []`, `current_task_id is None`, and no task fields appear in serialized V0.7 context.

Require `TraceRecorder.emit` with `task_id="task-1"` to preserve the ID in subscribers, history, and the saved run record. Existing callers that omit it must serialize `task_id: null`.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_context_builder tests.test_trace_recorder
```

- [ ] **Step 3: Implement minimal plumbing**

Add optional `task_plan` and `current_task_id` parameters at the end of `ContextBuilder.build`, copy the list, and pass them into `AgentContext`. Add optional `task_id` at the end of `TraceRecorder.emit` and pass it into `TraceEvent`.

- [ ] **Step 4: Run focused tests and verify GREEN**

Expected: PASS with all pre-V0.8 tests unchanged.

## Task 4: Integrate planning into the existing Agent Loop

**Files:**

- Modify: `src/min_agent/agent_loop.py`
- Modify: `tests/test_agent_loop.py`
- Modify: `tests/test_permission_flow.py`

- [ ] **Step 1: Add a scripted successful-plan test**

Create a local scripted decision model that returns, in order:

```python
AgentAction.create_plan(
    [
        TaskDefinition("task-1", "查看文件", "成功列出目录"),
        TaskDefinition("task-2", "读取资料", "成功读取 notes.md"),
    ],
    "Composite goal needs two outcomes",
)
AgentAction.tool_call("list_dir", {"path": "."}, "Need listing")
AgentAction.complete_task("task-1", "list_dir succeeded", [1], "Criterion met")
AgentAction.tool_call("read_file", {"path": "notes.md"}, "Need content")
AgentAction.complete_task("task-2", "read_file succeeded", [2], "Criterion met")
AgentAction.final_answer("done", "All tasks completed")
```

Assert:

- `plan_created` occurs before the first `tool_started`;
- the `plan_created` snapshot contains two pending tasks;
- each `task_started` snapshot has exactly one running task;
- `tool_started`, `tool_finished`, and `observation_added` carry the correct `task_id`;
- task 1 may contain multiple rounds without creating extra task cards;
- `task_completed(task-1)` precedes `task_started(task-2)`;
- the result succeeds only after both tasks are completed.

- [ ] **Step 2: Add composite failure tests**

Write separate tests for:

1. a tool returns `ToolResult(success=False, error="read_failed")`;
2. a permission callback returns `False`;
3. `complete_task` references the wrong ID;
4. `complete_task` has no successful Observation since task start;
5. the model returns failed `final_answer` while a task is running;
6. the model returns successful `final_answer` before all tasks complete;
7. max turns are exhausted during a running task.
8. the model proposes `create_plan` after any `tool_started` event has already occurred in the run.
9. the model proposes `create_plan` after a plan already exists for the run.

Every case must assert current=`failed`, pending=`skipped`, `run_failed`, no later task tool calls, and a deterministic final message containing completed/failed/skipped task sections. Permission rejection must also assert no denied `tool_started` event.

- [ ] **Step 3: Add simple-goal regression tests**

Run the existing two-action script (`tool_call`, `final_answer`) and assert there are no plan/task phases and every event `task_id` is `None`. Preserve the existing behavior where a simple-goal tool failure or permission rejection is returned to the model as an Observation for the next decision.

- [ ] **Step 4: Run Agent Loop tests and verify RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_agent_loop tests.test_permission_flow
```

- [ ] **Step 5: Implement plan-action handling**

Add `self.task_plan: TaskPlan | None = None`, `self._task_observations: list[Observation] = []`, and a run-local `self._has_started_tool: bool = False`. At each context build, pass the plan snapshot and current task ID. Emit every task-scoped event through a helper that supplies the current `task_id`.

Observation ownership is explicit:

- immediately after `start_next()` succeeds, clear `self._task_observations`;
- whenever an `observation_added` event is emitted while a task is running, append the same `Observation` object to `self._task_observations`;
- the `AgentContext.observations` list shown to the decision model during a running task must contain only the current task's working Observations, in the same order as `self._task_observations`;
- the 1-based indexes that the model cites in `complete_task.evidence_observation_indexes` are indexes into that current-task working list, not indexes into the global run history or trace event sequence;
- when handling `complete_task`, call `TaskPlan.complete_current(action.task_id, action.completion_evidence, action.evidence_observation_indexes, observations=self._task_observations)`;
- never let a task cite Observations from an earlier task; the state machine still verifies 1-based indexes and success results against the list passed for the current task;
- when a task fails or the run leaves composite mode, clear the current task Observation buffer after failure events are emitted.

Handle actions in this order:

```text
create_plan
complete_task
final_answer
tool_call
```

Rules:

- `create_plan` is legal only when no plan exists and no `tool_started` event has been emitted in the run. Track this with `_has_started_tool`; do not infer it from Observation count.
- An illegal `create_plan` is a model-protocol failure, not a recoverable Observation. Emit `llm_decision(status=failed)`, then `final_answer(status=failed)`, then `run_failed`, and do not create or mutate partial plan state.
- Emit `plan_created` with all tasks pending, call `start_next`, then emit `task_started`.
- `complete_task` is legal only for the current task. Let `TaskPlan.complete_current` verify the cited Observation indexes and results. Emit `task_completed`; if another task exists, start it and emit `task_started`.
- Completion evidence validation is structural: `TaskPlan` verifies current-task Observation indexes, uniqueness, range, and `result.success is True`; it does not parse free-text criteria or prove semantic relevance between criteria and cited output.
- A successful `final_answer` is legal for a composite run only when `all_completed()` is true.
- In composite mode, `final_answer`, `run_completed`, and `run_failed` are run-level events and must be emitted with `task_id=None`, even when they immediately follow a task-scoped event.
- A failed model action while a plan is active fails the current task immediately.
- Preflight validation failure, permission rejection, and `ToolResult.success=False` still create an `observation_added` event, then fail the active plan immediately.
- For simple runs, retain the existing V0.7 `continue` behavior after those Observations.
- On plan failure, emit `task_failed`, one `task_skipped` per pending task, `final_answer(status=failed)`, and `run_failed`; return immediately.
- The deterministic failure message must enumerate each task title under `已完成`, `失败`, or `跳过`, including the failure reason.

Do not put tool-name branches into the plan state machine or bypass `ToolRegistry`.

- [ ] **Step 6: Keep simple-goal loop budget stable and raise only composite budget**

Do not change the V0.7 simple-goal default budget of 8 turns. Add a separate composite-run budget path:

- keep `AgentLoop.max_turns` defaulting to `8` for simple goals and existing tests;
- add `AgentLoop.composite_max_turns` defaulting to `20`;
- before a plan exists, the loop is still governed by the simple budget;
- once a valid `plan_created` event exists, allow the run to continue up to the composite budget;
- if the constructor receives an explicit `max_turns`, preserve that explicit limit for both simple and composite runs unless a separate explicit `composite_max_turns` is also supplied.

Add tests showing:

- the four-task scenario can exceed eight decisions and still complete under the default composite budget;
- a simple looping model still stops at the V0.7 default of eight turns;
- a model that delays `create_plan` beyond the simple 8-turn budget fails deterministically before composite budget applies;
- an explicitly lower `max_turns` still truncates the composite scenario deterministically.

- [ ] **Step 7: Run focused tests and verify GREEN**

Expected: all Agent Loop and permission tests pass.

## Task 5: Teach FakeLLM the frozen composite demo

**Files:**

- Modify: `src/min_agent/fake_llm.py`
- Modify: `tests/test_fake_llm.py`

- [ ] **Step 1: Write failing classification tests**

Assert that the exact core goal produces a four-task `create_plan` action with these user-level titles and criteria:

```text
task-1 查看项目文件      成功获得 workspace 中可用 Markdown 文件列表
task-2 读取并整理资料    成功读取相关 Markdown 文件并形成摘要所需内容
task-3 获取当前时间      成功获得 run_command/get_current_time 的真实结果
task-4 生成并写入摘要    成功创建包含项目摘要和真实时间的 summary.md
```

Also assert:

- `现在几点？` still returns `run_command`, not `create_plan`;
- `总结整个 workspace。` still follows V0.7 file discovery, not a one-task plan;
- multiple tool calls alone do not trigger planning;
- a goal with time + explicit write target + workspace/project reading intent triggers planning.
- at least three boundary goals that contain overlapping words but only one verifiable outcome do not trigger planning, including:
  - `看看 project.md 里有没有提到时间，写到 notes.md。`
  - `读取 workspace 里的 notes.md，并把包含“当前时间”的句子写到 summary.md。`
  - `获取当前时间并写到 summary.md，不需要阅读项目资料。`

- [ ] **Step 2: Write failing per-task decision tests**

Construct `AgentContext` snapshots for each running task and assert the next action:

- task 1: `list_dir`, then `complete_task` citing the successful listing Observation;
- task 2: read relevant Markdown files up to the existing `MAX_FAKE_READS`, then `complete_task` citing every successful read used;
- task 3: `run_command/get_current_time`, then `complete_task` citing its successful Observation;
- task 4: `write_file(mode=create)` whose content includes both read material and the successful time Observation, then `complete_task` citing the successful write Observation;
- all completed: successful `final_answer` mentioning `summary.md`.

- [ ] **Step 3: Run FakeLLM tests and verify RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_fake_llm
```

- [ ] **Step 4: Implement goal-first routing**

The first branches of `decide()` must be:

```python
if context.task_plan:
    return self._decide_planned_goal(context)
if self._is_composite_goal(context.user_goal):
    return self._create_composite_plan(context.user_goal)
if self._is_time_query(context.user_goal):
    return self._decide_time(context)
```

`_is_composite_goal` must require all three signals: project/workspace reading intent, current-time intent, and an explicit writable Markdown target. Do not treat conjunction words or tool count alone as sufficient.

This narrow detector is intentional for V0.8 FakeLLM: it demonstrates the frozen composite demo and protects simple V0.7 paths. It is not a general composite-goal classifier. Do not add unrelated composite patterns such as comparison/report-writing unless the product design changes in a later version.

Use current task ID and successful Observations to choose actions. Reuse existing safe file selection, time Observation, and write-content helpers. Include a line such as `Generated at: <tool result>` in the generated file; do not obtain time from Python directly.

In `_decide_planned_goal`, never return `create_plan`; once `context.task_plan` exists, only act on `context.current_task_id` or complete/fail/finalize the existing plan state.

- [ ] **Step 5: Run all FakeLLM tests and verify GREEN**

Expected: new tests and all V0.1–V0.7 routing tests pass.

## Task 6: Extend the DeepSeek JSON contract safely

**Files:**

- Modify: `src/min_agent/deepseek_llm.py`
- Modify: `tests/test_deepseek_llm.py`

- [ ] **Step 1: Write parser tests for `create_plan`**

Accept only a JSON object shaped like:

```json
{
  "kind": "create_plan",
  "tasks": [
    {
      "task_id": "task-1",
      "title": "查看项目文件",
      "completion_criteria": "成功获得 workspace 文件列表"
    },
    {
      "task_id": "task-2",
      "title": "读取项目资料",
      "completion_criteria": "成功读取相关 Markdown 文件"
    }
  ],
  "reason": "The goal contains two ordered outcomes"
}
```

Reject non-list tasks, 1 or 6 tasks, non-object entries, non-sequential IDs, missing/blank strings, duplicate IDs, and extra task fields. Parser rejection must become a failed local `final_answer` with model-call metadata preserved; it must never partially create a plan.

If parser rejection happens after a plan already exists, the Agent Loop event chain must be:

```text
llm_decision(status=failed, raw model response preserved)
-> task_failed(current task)
-> task_skipped(each pending task)
-> final_answer(status=failed)
-> run_failed
```

If parser rejection happens before any plan exists, the event chain remains the existing model-failure path with `llm_decision(status=failed)`, `final_answer(status=failed)`, and `run_failed`, without task lifecycle events.

Add an Agent Loop test with a model that repeatedly returns invalid `create_plan` JSON before any plan exists. It must stop at `max_turns`, emit a clear failed final answer/run failure, and must not silently loop forever or create partial task state.

- [ ] **Step 2: Write parser tests for `complete_task`**

Accept only:

```json
{
  "kind": "complete_task",
  "task_id": "task-1",
  "completion_evidence": "Observation 1 contains a successful list_dir result",
  "evidence_observation_indexes": [1],
  "reason": "The current completion criterion is satisfied"
}
```

Reject missing/blank `task_id`, completion evidence, or reason; reject missing/non-list/empty indexes and non-integer or boolean entries. Whether indexes belong to the active task remains an Agent Loop/TaskPlan responsibility.

- [ ] **Step 3: Write prompt tests**

Assert the system/user prompt says:

- create a plan only for 2–5 ordered, independently verifiable user outcomes;
- never create a one-task plan;
- if a plan already exists for this run, do not propose another `create_plan`; act only on `current_task_id`;
- if no plan exists but the user goal is composite, propose `create_plan` immediately before using tools; the composite budget is available only after a valid `plan_created` event;
- tool-call count does not determine task count;
- after plan creation, act only on `current_task_id`;
- enumerate the current task's working Observations with stable 1-based indexes and return `complete_task` only with explicit successful current-task Observation references;
- do not change task definitions after creation;
- stop behavior is local and cannot be bypassed;
- output contract allows all four action kinds;
- current plan snapshot and current task ID appear in the user prompt.

- [ ] **Step 4: Run DeepSeek tests and verify RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_deepseek_llm
```

- [ ] **Step 5: Implement strict parsing and prompts**

Create small private parsers for task definitions and completion actions. Preserve existing unknown-tool checks and `run_command` structural validation. Do not call DeepSeek in tests.

- [ ] **Step 6: Run DeepSeek tests and verify GREEN**

Expected: all historical and new tests pass.

## Task 7: Complete CLI-level success and failure scenarios

**Files:**

- Modify: `src/min_agent/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_cli_scenarios.py`

- [ ] **Step 1: Add the complete success scenario**

Use `tempfile.TemporaryDirectory()` with `project.md` and `architecture.md`, patch `/bin/date` execution using the existing command-tool seam, and supply `y`, `y` for command and write permissions.

Run the exact goal from the frozen design. Assert:

- CLI exit code remains `0` for a completed Agent run;
- run record has four fixed task definitions before the first `tool_started`;
- status transitions are pending -> running -> completed in order;
- no two task snapshots contain multiple running tasks;
- all task-scoped tool events use the correct ID;
- `summary.md` is created inside only the temporary workspace;
- its content includes project material and the mocked time;
- both dangerous tools retain permission request/resolution before execution;
- final run status is completed.

- [ ] **Step 2: Add a middle-task rejection scenario**

Approve no permission for `run_command`. Assert tasks 1–2 completed, task 3 failed, task 4 skipped, overall run failed, no `tool_started(run_command)`, no `permission_requested(write_file)`, and no `summary.md`.

- [ ] **Step 3: Add a final-task rejection scenario**

Approve `run_command`, reject `write_file`. Assert task 4 failed, no `tool_started(write_file)`, previous tasks remain completed, and overall run failed.

- [ ] **Step 4: Add simple V0.7 regression scenarios**

Run `现在几点？` and a multi-file summary. Assert neither record contains `plan_created` or task phases, even though the latter uses multiple tool calls.

- [ ] **Step 5: Verify RED, implement only required CLI change, verify GREEN**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_cli tests.test_cli_scenarios
```

The only expected CLI production change is preserving the simple-goal 8-turn default while allowing the composite-run 20-turn budget through the Agent Loop constructor if CLI construction currently overrides defaults. Do not add plan approval prompts or new CLI flags.

## Task 8: Implement the frozen Trace Viewer hierarchy

**Files:**

- Modify: `web/trace_viewer.html`
- Modify: `web/trace_viewer.js`
- Modify: `web/trace_viewer.css`
- Modify: `tests/test_trace_viewer_source.py`

- [ ] **Step 1: Add source-structure tests before markup changes**

Require this DOM order:

```text
.run-status / #run-title
.summary-panel
#original-request
#result-panel / #final-result
#task-plan-panel
.layout
```

Require the plan panel contract:

```html
<section id="task-plan-panel" class="task-plan-panel" hidden>
  <div class="task-plan-heading"><h2>任务计划</h2></div>
  <strong id="task-progress-text"></strong>
  <div id="task-progress-value" class="progress-value"></div>
  <ol id="task-list" class="task-list"></ol>
</section>
```

Require `#selected-task-label` inside the execution-round panel and initially hidden. Keep all existing V0.4–V0.7 IDs/classes and reject form controls or approve/reject text.

- [ ] **Step 2: Add JavaScript source tests**

Require focused functions with these responsibilities:

```text
buildTaskPlan(events)       derive immutable definitions plus latest statuses
renderTaskPlan()            hide when no 2–5 task plan; render cards otherwise
selectTask(taskId)          change only Viewer selection state
roundsForSelectedTask()     filter rounds without discarding their raw events
taskIdForEvents(roundEvents) associate plan creation with task-1 and normal rounds by event.task_id
```

Tests must assert `textContent`/DOM node creation is used instead of `innerHTML`, failed/skipped CSS classes are distinct, and simple mode clears selected task state and hides both plan panel and label. Also assert `#selected-task-label` becomes visible when a task is selected and hides when there is no plan or `selectedTaskId` is `null`.

Add a CSS source assertion that every custom property referenced by new V0.8 selectors, such as `var(--green)`, `var(--red)`, or `var(--blue-soft)`, is defined in `web/trace_viewer.css` after the CSS change.

- [ ] **Step 3: Run source tests and verify RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_trace_viewer_source
```

- [ ] **Step 4: Add the conditional markup**

Insert the hidden plan panel after `.result` and before `.layout`. Add the hidden selected-task label below the existing rounds heading. Do not move or remove the original request, summary, final result, rounds, or detail modules.

- [ ] **Step 5: Extend Viewer state and rendering**

Add `selectedTaskId`. `buildTaskPlan` starts from `plan_created.output.tasks` and applies `task_started`, `task_completed`, `task_failed`, and `task_skipped` events by stable ID. It must reject malformed event data by returning no visible plan rather than throwing.

Selection rules:

- on valid `plan_created`, select the first task;
- while live, select the current running/failed task;
- user clicks override selection until a new lifecycle event changes the active task;
- completed/skipped tasks with no rounds show a clear empty state, not another task's rounds;
- no plan resets `selectedTaskId` to `null` and preserves existing V0.7 round selection.

Round rules:

- retain the existing Context Build grouping;
- use explicit event `task_id` for normal rounds;
- associate the plan-creation Context/Model/Plan events with the first task so the plan decision remains inspectable, but label that grouped round as `计划生成（任务 1 开始前）` in the round metadata/details so users do not confuse it with task-1 execution;
- buffer a newly emitted `task_started` event for the next context round when it belongs to a different task;
- include task completion/failure events in the current task's final round;
- never replace original event details with task-card summaries.

Concrete boundary example: for the raw event order `task_completed(task-1) -> task_started(task-2) -> context_built`, keep `task_completed(task-1)` in task-1's final round, keep the original raw-event order unchanged, and hold `task_started(task-2)` as the first event in task-2's next rendered round with the following `context_built`. This buffering is a Viewer grouping rule only; it must not delay SSE events or rewrite the saved run record.

Add task phases to `moduleForPhase`, flow labels, and event details.

Add source-level edge-case tests for:

- skipped tasks that have no rounds render a clear empty state instead of leaking another task's rounds;
- a single-round task remains selectable and shows only its own round;
- `plan_created` and its Context/Model/Plan events are associated with `task-1` and visibly labeled as plan generation before task-1 starts;
- the exact sequence `task_completed(task-1) -> task_started(task-2) -> context_built` puts the `context_built` event into task-2's first round, not task-1's detail trail.

- [ ] **Step 6: Copy the approved visual rules**

Diff against the existing `web/trace_viewer.css`, then port only the V0.8 selectors needed from `docs/superpowers/v0.8/trace-viewer-prototype.html`: `.task-plan-panel`, `.task-plan-heading`, `.task-progress`, `.progress-track`, `.progress-value`, `.task-list`, `.task-card`, `.task-card.*`, `.task-index`, `.task-status`, `.task-top`, `.task-error`, `.selected-task-label`, plus the updated `@media (max-width: 760px)` rules for `.task-list` and `.task-progress`. Also add any referenced custom properties that the current `:root` lacks, including `--blue`, `--blue-soft`, `--green`, `--green-soft`, `--red`, and `--red-soft`, so the source assertion from Step 2 proves the copied selectors have live values. Do not duplicate already-equivalent `.status`, `.summary-panel`, `.badge`, or `.event-step` styling. Do not introduce a front-end framework, external asset, or decorative redesign.

- [ ] **Step 7: Run source tests and verify GREEN**

Expected: all prior Viewer structure tests and new V0.8 tests pass.

## Task 9: Update user and operator documentation

**Files:**

- Modify: `README.md`
- Modify: `docs/runbook.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_project_testing_rules.py`

- [ ] **Step 1: Add documentation assertions**

Require V0.8 docs to mention the exact core goal, 2–5 tasks, simple-goal fallback, first-failure stop, existing per-tool permissions, no plan approval, and browser acceptance requirement.

- [ ] **Step 2: Update README**

Add a V0.8 section after V0.7 with the command, expected four-task plan, simple/composite distinction, and explicit non-goals. Do not imply production orchestration, dynamic planning, retries, parallelism, or web control.

- [ ] **Step 3: Update runbook**

Add:

- FakeLLM success steps with two permission approvals;
- run-record event-chain checks;
- run-command and write-file rejection checks;
- simple-goal regression check;
- real-browser checklist matching Task 11;
- workspace cleanup/retention policy.

- [ ] **Step 4: Finalize CHANGELOG V0.8**

Keep it product-facing: problem solved, visible effect, non-goals, and completion evidence. Do not turn it into a file list.

- [ ] **Step 5: Run documentation tests**

```bash
PYTHONPATH=src python3 -m unittest tests.test_project_testing_rules
```

Expected: PASS.

## Task 10: Full automated verification

**Files:** all changed implementation and test files.

- [ ] **Step 1: Run whitespace validation**

```bash
git diff --check
```

Expected: no output and exit code 0.

- [ ] **Step 2: Run the complete required suite**

```bash
python3 -m unittest discover -s tests
```

Expected: all tests pass. The suite needs local-port permission for `TraceServer`; if a sandbox returns `Operation not permitted`, rerun the identical command in the approved non-sandbox environment and record both results accurately.

- [ ] **Step 3: Inspect the exact diff scope**

```bash
git status --short
git diff --stat
git diff -- AGENTS.md CHANGELOG.md README.md docs/runbook.md src tests web docs/superpowers/v0.8
```

Expected: only declared V0.8 files, already-approved product assets, collaboration configuration, and collaboration records differ. Stop on undeclared writes.

- [ ] **Step 4: Recheck frozen boundaries**

Confirm no edits to product design or prototype, no dependency/config/secret changes, no raw shell command support, and no Viewer controls.

## Task 11: Agent scenario and real-browser acceptance

**Files/outputs:** no repository screenshot; use a temporary workspace outside the repository.

- [ ] **Step 1: Run the successful composite scenario**

Create a temporary workspace outside the repository containing `project.md` and `architecture.md`. Start the real CLI/TraceServer with FakeLLM, approve both dangerous actions, and keep the server open for at least 60 seconds after the run completes so the browser can inspect success, task filtering, and console state. Record the temporary path; do not delete it without user authorization. After inspection, stop the server with the same terminal/session interrupt used to launch it and verify no orphaned TraceServer process remains.

Verify the run record against this matrix:

| Check | Required evidence |
| --- | --- |
| Plan timing | `plan_created` before first `tool_started` |
| Fixed plan | exactly four unchanged task definitions |
| Sequential state | at most one `running`; ordered completion |
| Task/tool link | every scoped tool event has expected `task_id` |
| Permission safety | each dangerous tool requested/resolved before start |
| Real output | `summary.md` contains project material and command-returned time |
| Completion | four completed tasks, final answer, `run_completed` |

- [ ] **Step 2: Inspect in a real browser**

Using the running Viewer, confirm:

- page is non-empty and module order matches the frozen prototype;
- task panel shows four ordered cards and accurate progress;
- clicking each task filters its rounds;
- clicking a round updates the original step details;
- task 2 shows multiple rounds under one task card;
- Context Build still shows seven sources;
- command and permission details remain visible;
- no approve/reject/edit/retry controls exist;
- browser console has zero JavaScript errors.

- [ ] **Step 3: Verify failure mode in a real browser**

Run a second temporary-workspace scenario that rejects `run_command`. Confirm task 3 is red/failed, task 4 is gray/skipped with a reason, progress is not shown as successful completion, and no later write round exists.

- [ ] **Step 4: Verify simple V0.7 mode**

Run `现在几点？`. Confirm the entire task plan panel and selected-task label are hidden, while the original V0.7 rounds/details and command card still work.

- [ ] **Step 5: Verify responsive behavior**

At approximately 390 px width, confirm the `@media (max-width: 760px)` layout still produces one-column task cards, stacked round/detail regions, readable content, and no horizontal page overflow. No separate 390 px breakpoint is required unless this real-browser check fails.

- [ ] **Step 6: Report browser result honestly**

Only report `browser manual smoke: PASS` after all real-browser checks above. Source tests alone require `NOT RUN`. Do not save a screenshot unless separately approved.

## 4. Test and acceptance matrix

| Layer | Tests/validation | Product boundary proved |
| --- | --- | --- |
| Mechanism unit | `test_task_plan`, `test_types`, `test_context_builder`, `test_agent_loop`, `test_permission_flow` | fixed 2–5 plan, legal transitions, real Observation evidence, single running task, first-failure stop, simple-path compatibility |
| Decision adapters | `test_fake_llm`, `test_deepseek_llm` | correct simple/composite classification, strict JSON contract, no one-task plan, current-task-only execution |
| Agent scenarios | `test_cli_scenarios` success, command rejection, write rejection, simple time, simple multi-file | complete event chains, task/tool linkage, unchanged permission boundary, real output content |
| Viewer source regression | `test_trace_viewer_source` | DOM order, conditional panel, required IDs/classes, safe text rendering, V0.4–V0.7 preservation |
| Full regression | `python3 -m unittest discover -s tests` | all historical versions remain green |
| Real browser | success/failure/simple + task/round clicks + 390 px + console | rendered experience matches frozen prototype and is genuinely usable |
| Workspace scope | `git status`, diff inspection, frozen hashes | no undeclared/protected writes |

## 5. Cleanup and retained artifacts

- Automated tests must use `TemporaryDirectory` and create no repository run records or workspace output.
- Manual browser acceptance uses temporary workspaces outside the repository. Record and retain them until the user authorizes deletion.
- Do not create screenshots, browser logs, downloaded assets, package caches, or generated fixtures in the repository.
- Keep the approved product design, prototype, this implementation plan, collaboration configuration, and collaboration review records.
- Do not delete existing `runs/` history.

## 6. Completion handoff

Implementation is acceptable only when every automated layer passes, the real browser matrix passes, the diff matches the declared scope, and Codex independently inspects the implementation rather than relying on the external executor's report.

Stop before any commit, push, merge, tag, release, deployment, or cleanup. Report the final diff, test counts, scenario evidence, browser result, retained temporary artifacts, and any unresolved risk for separate user decisions.
