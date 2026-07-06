# min-agent-demo V0.7 Controlled Command Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. If the executing model does not provide these skills, follow the checklist in order without merging tasks or skipping verification.

**Goal:** Add one permission-gated `run_command` tool that can execute only the predefined `get_current_time` action, return structured process results to the Agent Loop, and explain the complete flow in Trace Viewer without regressing V0.5 or V0.6.

**Architecture:** Keep `AgentLoop` tool-agnostic. A local command registry owns immutable command recipes; a command tool validates and executes a recipe without a shell; `ToolRegistry` supplies generic preflight validation and permission details before `AgentLoop` requests approval. FakeLLM and DeepSeek can select `run_command`, but neither can provide raw commands or parameters.

**Tech Stack:** Python standard library (`dataclasses`, `subprocess`, `time`, `pathlib`, `unittest`), existing vanilla HTML/CSS/JavaScript Trace Viewer, existing `ToolRegistry`, `TraceRecorder`, and structured `AgentAction`/`ToolResult` contracts.

---

## Executor contract

Before changing code, read these files completely:

```text
AGENTS.md
docs/superpowers/v0.7/product-design.md
docs/superpowers/v0.7/trace-viewer-prototype.html
```

Hard constraints:

- Do not install dependencies.
- Do not create or read `.env`.
- Do not use a real DeepSeek API key in tests.
- Do not allow raw command strings, custom arguments, pipes, redirects, shell operators, background tasks, stdin, or TTY.
- Do not special-case `run_command` execution inside `AgentLoop`.
- Do not remove or merge the seven V0.6 context-source cards.
- Do not add approve/reject controls to Trace Viewer.
- Do not claim `browser manual smoke: PASS` from source inspection.
- Do not commit, push, rebase, reset, tag, or delete files unless the user separately authorizes that action.
- The local interpreter is currently Python 3.9.6. Preserve `from __future__ import annotations` in new Python modules so the existing checkout remains testable while the documented minimum remains Python 3.10+.

## Final user-visible effect

Running:

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "现在几点？" \
  --workspace examples/workspace
```

must produce this path:

```text
Context Build
-> Model Decision(run_command/get_current_time)
-> Permission Requested
-> user enters y
-> Permission Resolved(approved=true)
-> Tool Started(run_command)
-> Tool Finished(exit_code=0)
-> Observation Added
-> next Context Build
-> Final Answer using the returned local time
```

The CLI permission prompt must show the action ID, resolved command, workspace, reason, and risk. The Viewer must show the command as a normal-sized Tool step with a `>_` icon, `COMMAND` label, and thin purple border.

## File responsibility map

### Create

- `src/min_agent/command_registry.py`: immutable command definitions, exact lookup, validation, and default `get_current_time` registration.
- `src/min_agent/tools/command.py`: no-shell process execution, timeout, output truncation, and structured ToolResult creation.
- `tests/test_command_registry.py`: recipe lookup and invalid argument tests.
- `tests/test_command_tool.py`: success, timeout, nonzero exit, startup failure, truncation, workspace, and no-shell tests.

### Modify

- `AGENTS.md`: add V0.7 boundary and command safety rules before implementation.
- `src/min_agent/tool_registry.py`: generic validator and permission-description hooks.
- `src/min_agent/agent_loop.py`: validate before approval; pass resolved permission details through Trace and CLI callback.
- `src/min_agent/cli.py`: register `run_command` and render command-specific permission information.
- `src/min_agent/types.py`: add `args_schema` to model-visible `ToolCatalogEntry`.
- `src/min_agent/context_loader.py`: copy each ToolSpec schema into the tool catalog.
- `src/min_agent/fake_llm.py`: choose `get_current_time` from goal and Observation state.
- `src/min_agent/deepseek_llm.py`: expose the model-visible command schema and validate only AgentAction argument structure.
- `web/trace_viewer.js`: specialized command-step rendering while retaining generic event rendering.
- `web/trace_viewer.css`: coordinated command type styling copied from the approved prototype.
- `tests/test_tool_registry.py`, `tests/test_permission_flow.py`, `tests/test_cli.py`, `tests/test_context_loader.py`, `tests/test_fake_llm.py`, `tests/test_deepseek_llm.py`, `tests/test_cli_scenarios.py`, `tests/test_trace_viewer_source.py`: regression and V0.7 coverage.
- `README.md`, `docs/runbook.md`, `CHANGELOG.md`: usage, operator flow, boundaries, and completion record.

## Task 1: Lock V0.7 project rules

**Files:**

- Modify: `AGENTS.md`
- Read: `docs/superpowers/v0.7/product-design.md`

- [ ] **Step 1: Add the V0.7 boundary after V0.6**

Add a concise section that states:

```markdown
## V0.7 边界

V0.7 在 V0.6 基础上只增加：

- `run_command` 权限工具
- 本地预定义命令注册机制
- `get_current_time` 当前时间动作
- 固定 workspace、5 秒超时和 stdout/stderr 分别 4096 字符截断
- Trace Viewer 命令执行解释性展示

V0.7 仍然不做：

- 模型生成的任意命令
- 原始命令字符串或自定义参数
- shell、管道、重定向、后台或交互式进程
- 网页批准权限
- 长期记忆、多 Agent、MCP、Hook、插件系统
```

- [ ] **Step 2: Add V0.7 command safety rules**

Record these enforceable rules:

```markdown
## V0.7 命令安全规则

- 模型只能返回 `run_command` 和 `command_id=get_current_time`。
- 命令由本地注册表解析为固定参数数组。
- 未知或非法 `command_id` 必须在权限申请前拒绝。
- 每次执行命令都必须经过 CLI 确认。
- 命令执行不得经过 shell。
- 用户拒绝后不能出现 `tool_started(run_command)`。
- 超时、非零退出码、启动失败和输出截断必须形成结构化 ToolResult。
```

- [ ] **Step 3: Verify the rule text**

Run:

```bash
rg -n "V0.7 边界|V0.7 命令安全规则|run_command|get_current_time" AGENTS.md
```

Expected: both headings and all required capability names are present.

- [ ] **Step 4: Stop at the Git checkpoint**

Run `git diff -- AGENTS.md`. Do not commit without explicit user authorization.

## Task 2: Build the predefined command registry

**Files:**

- Create: `src/min_agent/command_registry.py`
- Create: `tests/test_command_registry.py`

- [ ] **Step 1: Write failing registry tests**

Tests must assert the exact recipe and strict input shape:

```python
from min_agent.command_registry import build_default_command_registry


class CommandRegistryTest(unittest.TestCase):
    def test_get_current_time_has_fixed_recipe(self) -> None:
        registry = build_default_command_registry()
        definition = registry.get("get_current_time")
        self.assertIsNotNone(definition)
        self.assertEqual(definition.argv, ("/bin/date", "+%Y-%m-%d %H:%M:%S %Z"))
        self.assertEqual(definition.timeout_seconds, 5.0)
        self.assertEqual(definition.output_limit, 4096)

    def test_validate_args_accepts_only_command_id(self) -> None:
        registry = build_default_command_registry()
        self.assertIsNone(registry.validate_args({"command_id": "get_current_time"}))
        result = registry.validate_args({"command_id": "get_current_time", "command": "date"})
        self.assertEqual(result.error, "invalid_command_args")

    def test_unknown_command_id_is_rejected(self) -> None:
        registry = build_default_command_registry()
        result = registry.validate_args({"command_id": "delete_everything"})
        self.assertEqual(result.error, "unknown_command_id")
```

Also cover missing and non-string `command_id`.

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_command_registry
```

Expected: FAIL because `min_agent.command_registry` does not exist.

- [ ] **Step 3: Implement the registry**

Use these public contracts:

```python
from __future__ import annotations


@dataclass(frozen=True)
class CommandDefinition:
    command_id: str
    description: str
    argv: tuple[str, ...]
    display_command: str
    risk: str
    timeout_seconds: float = 5.0
    output_limit: int = 4096


class CommandRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, CommandDefinition] = {}

    def register(self, definition: CommandDefinition) -> None:
        if definition.command_id in self._definitions:
            raise ValueError(f"command already registered: {definition.command_id}")
        self._definitions[definition.command_id] = definition

    def get(self, command_id: str) -> CommandDefinition | None:
        return self._definitions.get(command_id)

    def validate_args(self, args: dict[str, Any]) -> ToolResult | None:
        if set(args) != {"command_id"} or not isinstance(args.get("command_id"), str):
            return ToolResult(success=False, error="invalid_command_args")
        if self.get(args["command_id"]) is None:
            return ToolResult(success=False, error="unknown_command_id")
        return None

    def permission_details(self, args: dict[str, Any], workspace: Path) -> dict[str, Any]:
        definition = self._definitions[args["command_id"]]
        return {
            "command_id": definition.command_id,
            "command": definition.display_command,
            "workspace": str(workspace),
            "risk": definition.risk,
        }
```

`validate_args` must require exactly `{"command_id": <string>}`. Register only:

```python
CommandDefinition(
    command_id="get_current_time",
    description="Get the current local system time.",
    argv=("/bin/date", "+%Y-%m-%d %H:%M:%S %Z"),
    display_command='/bin/date "+%Y-%m-%d %H:%M:%S %Z"',
    risk="该命令只读取本机当前时间，不修改文件、不访问网络。",
)
```

- [ ] **Step 4: Run registry tests and verify GREEN**

Expected: all tests in `tests.test_command_registry` pass.

- [ ] **Step 5: Stop at the Git checkpoint**

Inspect only the two task files. Do not commit.

## Task 3: Implement the no-shell command tool

**Files:**

- Create: `src/min_agent/tools/command.py`
- Create: `tests/test_command_tool.py`

- [ ] **Step 1: Write failing execution tests**

Inject a fake runner; do not depend on wall-clock output for unit tests. Cover:

```python
result = run_command(workspace, {"command_id": "get_current_time"}, registry, runner=fake_runner)
self.assertTrue(result.success)
self.assertEqual(captured["args"], ["/bin/date", "+%Y-%m-%d %H:%M:%S %Z"])
self.assertEqual(captured["cwd"], str(workspace))
self.assertFalse(captured["shell"])
self.assertEqual(captured["timeout"], 5.0)
self.assertEqual(result.metadata["exit_code"], 0)
self.assertEqual(result.content, "2026-07-03 10:30:21 CST")
```

Add separate tests for:

- unknown command ID: runner is never called;
- `subprocess.TimeoutExpired`: `error == "command_timeout"`, `timed_out is True`;
- nonzero return code: `success is False`, stdout/stderr retained;
- `FileNotFoundError` and `OSError`: safe `command_start_failed` error;
- stdout and stderr longer than 4096 characters: truncated flags true, stored lengths 4096, and the stored values equal the first 4096 characters rather than the tail or a middle slice;
- surrounding newline removed from successful date output.

Use distinguishable prefixes and suffixes so truncation direction is proven:

```python
original_stdout = "STDOUT-BEGIN-" + ("x" * 5000) + "-STDOUT-END"
original_stderr = "STDERR-BEGIN-" + ("y" * 5000) + "-STDERR-END"
self.assertEqual(result.metadata["stdout"], original_stdout[:4096])
self.assertEqual(result.metadata["stderr"], original_stderr[:4096])
self.assertTrue(result.metadata["stdout"].startswith("STDOUT-BEGIN-"))
self.assertTrue(result.metadata["stderr"].startswith("STDERR-BEGIN-"))
self.assertTrue(result.metadata["stdout_truncated"])
self.assertTrue(result.metadata["stderr_truncated"])
```

- [ ] **Step 2: Run command-tool tests and verify RED**

Expected: FAIL because `min_agent.tools.command` does not exist.

- [ ] **Step 3: Implement `run_command`**

Required signature:

```python
from __future__ import annotations


def run_command(
    workspace: Path,
    args: dict[str, Any],
    registry: CommandRegistry,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
) -> ToolResult:
```

Resolve `process_runner = runner or subprocess.run`, then call it with:

```python
process_runner(
    list(definition.argv),
    cwd=str(workspace),
    capture_output=True,
    text=True,
    timeout=definition.timeout_seconds,
    shell=False,
    check=False,
)
```

Metadata must contain `command_id`, `display_command`, `exit_code`, `duration_ms`, `stdout`, `stderr`, `stdout_truncated`, `stderr_truncated`, and `timed_out`. Catch only expected process errors and never include environment variables in errors or metadata.

- [ ] **Step 4: Run tests and verify GREEN**

Run both new modules. Expected: `OK`.

- [ ] **Step 5: Stop at the Git checkpoint**

Do not commit.

## Task 4: Add generic preflight and permission details

**Files:**

- Modify: `src/min_agent/tool_registry.py`
- Modify: `src/min_agent/agent_loop.py`
- Modify: `tests/test_tool_registry.py`
- Modify: `tests/test_permission_flow.py`

- [ ] **Step 1: Write failing ToolRegistry tests**

Define generic hook types:

```python
ToolValidator = Callable[[dict[str, Any]], ToolResult | None]
PermissionDescriber = Callable[[dict[str, Any]], dict[str, Any]]
```

Tests must prove `validate_call` returns the validator error, `permission_details` returns resolved details, and tools without hooks keep existing behavior.

- [ ] **Step 2: Write failing AgentLoop tests**

Add tests proving:

- invalid command args create an Observation without `permission_requested` or `tool_started`;
- valid permission details appear in `permission_requested.input["details"]`;
- callback receives `(action, details)`;
- rejected calls still never emit `tool_started`;
- existing `write_file` approval and rejection remain unchanged.

- [ ] **Step 3: Run targeted tests and verify RED**

```bash
PYTHONPATH=src python3 -m unittest tests.test_tool_registry tests.test_permission_flow
```

Expected: failures for missing hook APIs and callback signature.

- [ ] **Step 4: Extend ToolRegistry without tool-specific branching**

Extend `register` with optional keyword-only `validator` and `permission_describer`. Add:

```python
def validate_call(self, name: str, args: dict[str, Any]) -> ToolResult | None:
    validator = self._validators.get(name)
    return validator(args) if validator is not None else None

def permission_details(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
    describer = self._permission_describers.get(name)
    return describer(args) if describer is not None else {}
```

- [ ] **Step 5: Change AgentLoop ordering**

Immediately after confirming `action.tool_name` exists:

```text
validate_call
-> if invalid: observation_added and continue
-> resolve permission_details
-> permission_requested
-> permission callback
-> permission_resolved
-> tool_started
```

Change the callback type to:

```python
Callable[[AgentAction, dict[str, Any]], bool]
```

Include `details` in both permission events. Do not call a concrete command module from `AgentLoop`.

- [ ] **Step 6: Run targeted tests and verify GREEN**

Expected: `OK`, including all pre-existing V0.5 permission tests.

- [ ] **Step 7: Stop at the Git checkpoint**

Do not commit.

## Task 5: Register the CLI tool and render its prompt

**Files:**

- Modify: `src/min_agent/cli.py`
- Modify: `src/min_agent/types.py`
- Modify: `src/min_agent/context_loader.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_context_loader.py`

- [ ] **Step 1: Write failing CLI tests**

Update the tool-set expectation to:

```python
{"read_file", "list_dir", "write_file", "run_command"}
```

Assert `run_command.requires_permission is True`, schema is exactly `{"command_id": "string"}`, and its validator blocks unknown IDs.

Add a context-loader test asserting the model-visible catalog entry serializes as:

```python
{
    "name": "run_command",
    "description": "Run one predefined local command action after approval.",
    "args_schema": {"command_id": "string"},
    "requires_permission": True,
}
```

Capture stdout for `confirm_tool_call` and assert the command prompt contains:

```text
Permission required: run_command
Action: get_current_time
Command: /bin/date "+%Y-%m-%d %H:%M:%S %Z"
Workspace: <workspace>
Risk: 该命令只读取本机当前时间，不修改文件、不访问网络。
Approve? [y/N]
```

Retain the existing write-file preview tests.

- [ ] **Step 2: Verify RED**

Run `tests.test_cli` and `tests.test_context_loader`. Expected: old three-tool assertions and the new model-visible schema assertion fail.

- [ ] **Step 3: Register run_command and propagate its schema**

Build one default `CommandRegistry` in `build_tool_registry`; register the handler, validator, and permission describer. The existing CLI ToolSpec definitions for `read_file`, `list_dir`, and `write_file` already have schemas; preserve them unchanged.

Add the new field after `requires_permission` so existing direct constructions remain compatible:

```python
@dataclass(frozen=True)
class ToolCatalogEntry:
    name: str
    description: str
    requires_permission: bool
    args_schema: dict[str, Any] = field(default_factory=dict)
```

Update `ContextLoader.build_tool_catalog` to copy every schema into an independent dictionary:

```python
ToolCatalogEntry(
    name=tool.name,
    description=tool.description,
    requires_permission=tool.requires_permission,
    args_schema=dict(tool.args_schema),
)
```

This must preserve the three existing schemas, expose `run_command` as `{"command_id": "string"}`, and allow older tests or callers that omit `args_schema` to receive `{}` without sharing mutable state. Update `confirm_tool_call` to accept `details` and render command fields when present, while retaining Path and Preview for `write_file`.

- [ ] **Step 4: Verify GREEN**

Run `tests.test_cli` and `tests.test_context_loader`. Expected: `OK`.

- [ ] **Step 5: Stop at the Git checkpoint**

Do not commit.

## Task 6: Teach FakeLLM the real-time scenario

**Files:**

- Modify: `src/min_agent/fake_llm.py`
- Modify: `tests/test_fake_llm.py`

- [ ] **Step 1: Write failing decision tests**

Cover Chinese and English time goals, successful result, rejection, execution failure, and missing tool. Use observations with `tool_name="run_command"` and `args={"command_id":"get_current_time"}`.

Expected decisions:

```text
现在几点？ + no Observation -> tool_call(run_command/get_current_time)
successful Observation -> final answer containing returned time
permission rejected -> failed final answer and no retry
command timeout/nonzero -> failed final answer using safe error
run_command unavailable -> failed final answer explaining missing capability
```

- [ ] **Step 2: Verify RED**

Run `tests.test_fake_llm`. Expected: new time tests fail because FakeLLM currently falls into file discovery.

- [ ] **Step 3: Implement goal-first command routing**

At the start of `decide`, route only explicit current-time intent such as `现在几点`, `当前时间`, `current time`, or `what time`. Base all subsequent decisions on the latest matching Observation, not a turn counter.

- [ ] **Step 4: Verify GREEN and file regressions**

```bash
PYTHONPATH=src python3 -m unittest tests.test_fake_llm tests.test_cli_scenarios
```

Expected: existing read/write scenarios remain green.

- [ ] **Step 5: Stop at the Git checkpoint**

Do not commit.

## Task 7: Constrain DeepSeek command actions

**Files:**

- Modify: `src/min_agent/deepseek_llm.py`
- Modify: `tests/test_deepseek_llm.py`

- [ ] **Step 1: Write failing prompt and parser tests**

Dependency from Task 5: `build_tool_registry` registers `run_command`; `ContextBuilder` converts all registered `ToolSpec` values into `context.tool_catalog`; `_user_prompt` serializes that catalog into `available_tools`. This project does not send a DeepSeek Chat Completions API `tools` array.

Assert the system prompt includes the only allowed command example:

```json
{"kind":"tool_call","tool_name":"run_command","args":{"command_id":"get_current_time"},"reason":"Need current local time"}
```

Build an AgentContext whose tool catalog contains:

```python
ToolCatalogEntry(
    name="run_command",
    description="Run one predefined local command action after approval.",
    requires_permission=True,
)
```

Assert the JSON produced by `_user_prompt` contains a matching `available_tools` entry with `args_schema == {"command_id": "string"}` and `requires_permission is True`.

Assert parsing accepts a string `command_id`. Parser-level rejection is limited to structural errors:

- `tool_name` is missing or not a string;
- `args` is not a dictionary;
- `run_command.args.command_id` is missing or not a string.

Assert an unknown string ID such as `delete_everything` is preserved in an AgentAction and reaches the generic `ToolRegistry.validate_call -> CommandRegistry.validate_args` preflight tested in Tasks 4 and 8. The parser must not decide which registered command IDs are allowed. Extra keys such as `command`, `argv`, `cwd`, `env`, or `timeout` must likewise reach the exact-shape registry validator and be rejected before permission.

Existing list/read/write parsing tests must remain green.

- [ ] **Step 2: Verify RED**

Run `tests.test_deepseek_llm`. Expected: new command contract assertions fail.

- [ ] **Step 3: Update prompt and structural validation**

Add the `get_current_time` usage example to `_system_prompt`. In `_action_from_data`, when `tool_name == "run_command"`, validate only that `args` is a dictionary and `args["command_id"]` is a string, then construct AgentAction. Do not hard-code `get_current_time` as the only legal value here. `ToolRegistry.validate_call -> CommandRegistry.validate_args` remains the single authority for allowed IDs and exact argument keys.

- [ ] **Step 4: Verify GREEN**

Run `tests.test_deepseek_llm`. Expected: `OK` without network calls.

- [ ] **Step 5: Stop at the Git checkpoint**

Do not commit.

## Task 8: Add complete CLI scenario coverage

**Files:**

- Modify: `tests/test_cli_scenarios.py`
- Modify: `tests/test_context_loader.py`

- [ ] **Step 1: Add approved-time scenario**

Patch the command runner to deterministic output. Run `main` with FakeLLM and `input=y`. Assert the run record contains this ordered subsequence:

```python
[
    "context_built", "llm_decision", "permission_requested",
    "permission_resolved", "tool_started", "tool_finished",
    "observation_added", "context_built", "llm_decision", "final_answer",
]
```

Assert `permission_requested.input.details` contains the exact display command; `tool_finished.output.metadata.exit_code == 0`; final answer contains the fake time.

Then select the two `context_built` events in step order. Assert the second context snapshot contains the command result in Working Observations:

```python
context_events = [event for event in record["events"] if event["phase"] == "context_built"]
self.assertEqual(len(context_events), 2)
observations = context_events[1]["output"]["observations"]
self.assertTrue(any(
    observation["tool_name"] == "run_command"
    and observation["result"]["content"] == "2026-07-03 10:30:21 CST"
    for observation in observations
))
```

- [ ] **Step 2: Add rejected-time scenario**

Use `input=n`. Assert `approved is False`, rejection Observation exists, and no `tool_started` event names `run_command`.

- [ ] **Step 3: Add invalid and failed-command scenarios**

Cover unknown ID preflight and timeout ToolResult. Assert both finish with observable failure and do not crash the CLI.

Also extend the tool-catalog test in `tests/test_context_loader.py` to assert that a registered `run_command` entry is present and has `requires_permission=True`.

- [ ] **Step 4: Run scenarios**

```bash
PYTHONPATH=src python3 -m unittest tests.test_cli_scenarios
```

Expected: `OK`; no real command or network use in scenario tests.

- [ ] **Step 5: Stop at the Git checkpoint**

Do not commit.

## Task 9: Implement the approved Trace Viewer increment

**Files:**

- Modify: `web/trace_viewer.js`
- Modify: `web/trace_viewer.css`
- Modify: `tests/test_trace_viewer_source.py`
- Visual reference: `docs/superpowers/v0.7/trace-viewer-prototype.html`

- [ ] **Step 1: Write failing source-structure tests**

Require:

- `buildDisplaySteps` function that converts raw events into display steps without modifying `state.events`;
- `renderCommandStep` function;
- `isRunCommandStart` or equivalent helper;
- `.command-step`, `.command-label`, and command icon styles;
- visible labels for 预定义动作, 实际命令, 工作目录, exit code, duration, stdout, stderr, and truncation;
- `buildFlowItems` still renders `Tool: run_command` through the generic tool path;
- all seven V0.6 context source tokens remain;
- no approve/reject/input command controls.

Add a source-contract fixture description with adjacent raw events:

```text
context_built
llm_decision
permission_requested
permission_resolved
tool_started(run_command)
tool_finished
observation_added
```

The source test must assert that `buildDisplaySteps` contains the adjacent-pair branch, retains `startedEvent` and `finishedEvent`, skips one consumed finish event, and has a `finishedEvent: null` pending path. Source-token assertions do not prove the returned count; the six-step result and non-mutation requirement must be verified against a real rendered scenario in Step 6.

- [ ] **Step 2: Verify RED**

Run `tests.test_trace_viewer_source`. Expected: only new V0.7 assertions fail.

- [ ] **Step 3: Add display-step aggregation and command rendering**

Implement `buildDisplaySteps(events)` as a presentation-only pass. When it encounters `tool_started` with `input.tool_name == "run_command"`, pair it only with the immediately following `tool_finished` event. Emit one object such as `{kind: "command", startedEvent, finishedEvent}` and skip the consumed finish event. If the finish event has not arrived yet, emit `{kind: "command", startedEvent, finishedEvent: null}` so the live Viewer shows a pending card. All non-command events remain one display step each and preserve order.

Change round rendering to iterate display steps rather than raw events. Keep `round.events` intact for raw trace inspection and Context Build comparisons, but compute the visible step count from `buildDisplaySteps(round.events).length`; the approved command round therefore shows six steps rather than seven raw events.

`renderCommandStep` must create one normal-sized `.event-step.command-step` card. Its existing `.step-io-grid` has Input on the left from `startedEvent.input` and Output on the right from `finishedEvent.output`. Include both raw TraceEvent objects under the card's raw-event details. Do not render the paired `tool_finished` as a second card. Use DOM APIs and `textContent`; do not use `innerHTML`.

Style only with:

```css
.event-step.command-step { border-color: #d8b4fe; border-left: 3px solid #7e22ce; }
.command-label { background: #f3e8ff; color: #6b21a8; }
```

Do not add a top-level command panel.

- [ ] **Step 4: Verify source tests GREEN**

Expected: all `tests.test_trace_viewer_source` tests pass, including V0.4–V0.6 preservation assertions.

- [ ] **Step 5: Run a real local command scenario for browser data**

Use a temporary workspace or `examples/workspace`; do not create business files. Start the Viewer, run the approved time scenario, and retain the ignored run record long enough for browser inspection.

- [ ] **Step 6: Perform real browser smoke**

Verify in a real browser:

1. Page is not blank.
2. Summary, original request, final result, round list, and detail order match V0.6.
3. Context Build still shows five base and two dynamic cards.
4. Tool catalog contains four tools and marks `run_command` permission-required.
5. Permission request and resolution precede command execution.
6. Command step is normal-sized with `>_`, `COMMAND`, and thin purple border.
7. Command, workspace, exit code, duration, stdout/stderr, and truncation state are visible.
8. Next round Working Observations contains the time result.
9. The selected command round contains exactly six `.event-step` elements and exactly one `.command-step`; there is no second visible card for the paired `tool_finished` event.
10. The command card raw-event details contain both original TraceEvent objects, while the underlying run record still contains all seven raw events.
11. Round switching works.
12. Narrow layout remains readable.
13. Browser console has no JavaScript error.

Record exactly `browser manual smoke: PASS` only after all checks. Otherwise record `NOT RUN` or `FAIL` with the reason.

- [ ] **Step 7: Clean temporary artifacts**

Test-created temporary workspaces must self-clean. Do not delete manually created files without user approval. Ignored run records may remain unless the user authorizes cleanup.

## Task 10: Documentation and full verification

**Files:**

- Modify: `README.md`
- Modify: `docs/runbook.md`
- Modify: `CHANGELOG.md`
- Verify: all files changed by Tasks 1–9

- [ ] **Step 1: Update user documentation**

Add the exact time demo command, approval prompt, expected output shape, and these boundaries: predefined action only, approval every time, no shell, no arbitrary command, local timezone.

- [ ] **Step 2: Add the V0.7 changelog entry**

Explain the user-visible problem solved, the permission-visible experience, what V0.7 does not do, and completion criteria. Do not write a commit-file list.

- [ ] **Step 3: Run focused mechanism tests**

```bash
PYTHONPATH=src python3 -m unittest \
  tests.test_command_registry \
  tests.test_command_tool \
  tests.test_tool_registry \
  tests.test_permission_flow \
  tests.test_cli \
  tests.test_context_loader \
  tests.test_fake_llm \
  tests.test_deepseek_llm \
  tests.test_cli_scenarios \
  tests.test_trace_viewer_source
```

Expected: exit code 0 and final `OK`.

- [ ] **Step 4: Run the complete suite**

```bash
python3 -m unittest discover -s tests
```

Expected: exit code 0, zero failures, zero errors.

- [ ] **Step 5: Run repository hygiene checks**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended V0.7 files are changed or untracked.

- [ ] **Step 6: Verify the approved FakeLLM path manually**

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "现在几点？" \
  --workspace examples/workspace \
  --no-viewer \
  --no-browser \
  --step-delay 0
```

Enter `y`. Expected: the CLI displays the full permission request and returns the current local time. Confirm the run record shows the approved event chain.

- [ ] **Step 7: Verify the rejected path manually**

Run the same command and enter `n`. Expected: no command starts; final output explains the refusal.

- [ ] **Step 8: Do not run a real DeepSeek request by default**

The automated mocked-client tests are sufficient unless the user explicitly supplies authorization and credentials for a live request. Never persist the key.

- [ ] **Step 9: Produce the final validation report**

Report:

```text
unit tests: PASS/FAIL with command and count
approved CLI scenario: PASS/FAIL
rejected CLI scenario: PASS/FAIL
browser manual smoke: PASS/FAIL/NOT RUN
console JavaScript errors: count
temporary artifacts: retained/cleaned and why
git operations: none unless separately authorized
```

- [ ] **Step 10: Stop at the final Git checkpoint**

Do not commit, tag, merge, or push. Ask the user for the next action.

## Test acceptance matrix

| Layer | Required evidence | Must not be substituted with |
| --- | --- | --- |
| Command registry | exact recipe and strict args tests | prompt wording alone |
| Command execution | injected-runner success/failure tests | real `/bin/date` only |
| Permission mechanism | invalid-before-prompt, approve, reject event tests | CLI screenshot only |
| FakeLLM | goal/Observation state transitions | fixed turn count |
| DeepSeek | mocked response parsing and prompt contract | live API call |
| Agent scenario | ordered run-record event chain | isolated function tests |
| Viewer structure | source preservation tests | browser smoke only |
| Viewer usability | real browser and console inspection | source-token assertions |
| Full regression | complete unittest discovery | targeted V0.7 tests only |

## Completion gate

Do not report V0.7 complete until all conditions are true:

- Product-design requirements map to an implemented task above.
- Unknown command IDs never reach permission or process execution.
- User rejection never emits `tool_started(run_command)`.
- Approved execution uses fixed argv, fixed workspace, five-second timeout, 4096-character limits, and `shell=False`.
- V0.5 write approval tests remain green.
- V0.6 seven-source context tests remain green.
- Full unittest discovery passes.
- Real browser smoke passes with zero console errors.
- README, runbook, changelog, product design, prototype, implementation, and behavior agree.
- No unapproved Git operation has occurred.
