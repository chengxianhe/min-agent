# Plan Review Round 3

## Metadata

- `attempts`: `1`
- `cost_usd`: `0.436145`
- `task_id`: `min-agent-demo-v0.8`

## Normalized result

```json
{
  "findings": [
    {
      "evidence": "Implementation plan §1 constraint: 'V0.8 validates structural completion evidence... V0.8 does not implement semantic matching between free-text completion_criteria and arbitrary tool output content.' Product design §任务模型: '完成标准必须能被真实结果验证' and 验收标准 #6: '任务状态由真实 Observation 驱动'.",
      "id": "F1",
      "recommendation": "Add at least one Agent scenario test where the model cites correct Observation indexes but the cited content is semantically irrelevant to the completion_criteria, and confirm whether this is an accepted limitation or needs a test-gated guard. If accepted, document this explicitly in the product design as a V0.8 limitation, not just in the implementation plan.",
      "severity": "P1",
      "title": "Completion evidence is structural-only, not semantic"
    },
    {
      "evidence": "Implementation plan Task 4 Step 6: 'before a plan exists, the loop is still governed by the simple budget; once a valid plan_created event exists, allow the run to continue up to the composite budget.' If the model takes 8 turns analyzing before deciding to create a plan, the run fails before plan_created is ever emitted.",
      "id": "F2",
      "recommendation": "Either (a) add a test showing the model must propose create_plan within the simple budget and document this as a constraint, or (b) mention this edge case explicitly in the DeepSeek prompt so the model knows to create the plan early. This is particularly important since the model gets a separate context-build turn before each decision.",
      "severity": "P1",
      "title": "Simple-to-composite budget transition has unhandled edge case"
    },
    {
      "evidence": "Task 5 Step 1 requires FakeLLM to trigger planning only for goals with all three signals: project/workspace reading intent, current-time intent, and explicit writable Markdown target. The five boundary test cases all test variations that lack one signal. But no test covers a goal with 2–3 verifiable outcomes that don't match the three-signal pattern.",
      "id": "F3",
      "recommendation": "Confirm this narrow detection is intentional for the V0.8 demo. If FakeLLM is meant as a general composite detector, add at least one more test case with a different composite goal pattern (e.g., '对比 project.md 和 architecture.md，把不同点写进 diff-report.md'). If intentional, document it as a V0.8 FakeLLM limitation.",
      "severity": "P1",
      "title": "FakeLLM composite detection tied narrowly to demo scenario"
    },
    {
      "evidence": "Task 4 Step 5: model returns 1-based evidence_observation_indexes. TaskPlan.complete_current checks them against the task-local Observable list. The plan says 'start_next() records the current observation_count as the task's evidence boundary' but does not describe the arithmetic converting the model's 1-based global indexes to 0-based task-local list indexes.",
      "id": "F4",
      "recommendation": "Add explicit validation in test_task_plan.py for a task that starts when 3 global Observations exist, receives 2 new Observations, and the model cites indexes 4 and 5. Verify the state machine correctly maps these to the task's local Observations without off-by-one errors.",
      "severity": "P1",
      "title": "Observation index 1-based/0-based translation not specified"
    },
    {
      "evidence": "Task 9 Step 5 modifies tests/test_project_testing_rules.py and runs it with 'python3 -m unittest tests.test_project_testing_rules'. This file is not listed in AGENTS.md directory conventions and may not exist in the repository.",
      "id": "F5",
      "recommendation": "Before modifying, verify the file exists. If not, create it in a separate step or fold its assertions into an existing test file to avoid depending on a non-existent test module.",
      "severity": "P1",
      "title": "test_project_testing_rules.py may not exist"
    },
    {
      "evidence": "Task 8 Step 5: 'associate the plan-creation Context/Model/Plan events with the first task so the plan decision remains inspectable.' But plan_created is emitted before task_started(task-1). Selecting task-1 in the Viewer will show events that happened before task-1 was running.",
      "id": "F6",
      "recommendation": "Add a visual separator or label in the Viewer that distinguishes the plan-creation phase from task-1's own rounds, or update the product design to acknowledge this pragmatic conflation. Without it, users may be confused about when task-1 actually started.",
      "severity": "P2",
      "title": "Plan-creation events conflated with task-1 execution in Viewer"
    },
    {
      "evidence": "Task 6 Step 1: if model returns create_plan with invalid JSON, parser rejects it. AgentLoop treats as model failure. On next turn, model can try create_plan again because no plan exists and no tool has started. This repeats until max_turns.",
      "id": "F7",
      "recommendation": "Consider tracking create_plan rejection count and limiting retries to prevent useless cycles. At minimum, add a test showing the behavior is bounded by max_turns and produces a clear error message rather than silently looping.",
      "severity": "P2",
      "title": "DeepSeek parser rejection can loop until max_turns"
    },
    {
      "evidence": "Task 2 Step 1 tests 'modifying the caller's original task list after plan creation' but this only guards against external mutation of the input list. It does not test whether TaskPlan.snapshot() returns references to internal mutable state.",
      "id": "F8",
      "recommendation": "Add a test that calls snapshot(), mutates a returned TaskSnapshot field, calls snapshot() again, and asserts the values are unchanged — proving deep copy, not shallow reference.",
      "severity": "P2",
      "title": "TaskPlan snapshot immutability not fully tested"
    },
    {
      "evidence": "Task 8 Step 6: 'port only the V0.8 selectors needed from the prototype.' The prototype uses CSS custom properties (--green, --red, --blue-soft, etc.) that may not exist in the current web/trace_viewer.css. Direct copy-paste of selectors without porting the variable definitions will produce broken styles.",
      "id": "F9",
      "recommendation": "Add a source test or explicit step that verifies all CSS custom properties referenced by new V0.8 selectors are already defined in the existing trace_viewer.css or are added in this task. Include this in the test_trace_viewer_source.py checks.",
      "severity": "P2",
      "title": "CSS porting risk from prototype to production Viewer"
    },
    {
      "evidence": "Task 8 Step 5: 'buffer a newly emitted task_started event for the next context round when it belongs to a different task.' The buffering mechanism (when to flush, how to handle multiple buffered events, interaction with live SSE streaming) is not described.",
      "id": "F10",
      "recommendation": "Add a source test specifically for the buffer behavior: emit task_completed(task-1) → task_started(task-2) → context_built in sequence, and assert task-2's first round contains the context_built event and not task-1's.",
      "severity": "P3",
      "title": "Viewer task_started buffering is under-specified"
    },
    {
      "evidence": "Task 11 Step 1: 'keep the server open long enough for inspection.' No guidance on expected inspection duration or cleanup process.",
      "id": "F11",
      "recommendation": "Specify a minimum inspection window (e.g., 'keep server running for at least 60 seconds after the run completes to allow full browser inspection') and document how to stop the server cleanly without leaving orphaned processes.",
      "severity": "P3",
      "title": "Browser acceptance server timeout not specified"
    }
  ],
  "pass": true,
  "schema_version": 1,
  "stage": "plan_review",
  "summary": "Implementation plan is structurally sound and covers all declared V0.8 capabilities with appropriate test gates. No P0 issues. Five P1 gaps around semantic evidence validation, budget transition edge case, FakeLLM detection narrowness, Observation index translation ambiguity, and missing test for `test_project_testing_rules.py` file existence. Six P2/P3 findings cover viewer rendering precision, CSS porting risk, and documentation reference integrity."
}
```
