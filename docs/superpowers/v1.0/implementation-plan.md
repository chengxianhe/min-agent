# min-agent-demo V1.0 Local Web Agent Implementation Plan

> **For DeepSeek executor:** Execute this plan task by task in the listed order. Use test-first changes and preserve every frozen boundary in this document. Do not use subagents, merge tasks, skip RED/GREEN verification, delete files, clean generated files, commit, push, merge, rebase, reset, tag, install dependencies, modify `.env`, secrets, CI/CD, or system configuration without separate user authorization.

**Goal:** Add one long-running local Web Agent service that lets a single user launch Fake or DeepSeek runs, resolve dangerous-tool permissions, inspect the live V0.9 Viewer, and replay saved runs without restarting the service for each goal.

**Architecture:** Keep `AgentLoop`, `ToolRegistry`, workspace tools, TraceEvent, and run records as the execution source of truth. A `RunManager` owns at most one active background Agent thread, a process-memory `SessionKeyStore` supplies DeepSeek credentials only to Web-created DeepSeek runs, and a condition-based `PermissionBroker` blocks only the Agent worker while the `ThreadingHTTPServer` remains responsive. A separate `WebAgentServer` exposes same-origin JSON/SSE APIs and the three-page Web shell. Extract the existing Viewer state/render logic into one reusable browser core so the legacy CLI Viewer and V1.0 Web app render the same TraceEvent contract.

**Tech Stack:** Python 3.10+ standard library only (`argparse`, `dataclasses`, `http.server`, `http.client`, `json`, `pathlib`, `queue`, `threading`, `typing`, `unittest`), the existing DeepSeek HTTP client, vanilla HTML/CSS/JavaScript, existing SSE transport, and existing JSON run records. Do not add a Python package, frontend framework, database, browser storage library, or model SDK.

---

## 1. Frozen inputs and execution contract

Read these files completely before changing implementation:

```text
AGENTS.md
docs/superpowers/v1.0/product-design.md
docs/superpowers/v1.0/web-agent-prototype.html
docs/superpowers/v1.0/implementation-plan.md
```

Also inspect the current implementation and tests before editing:

```text
src/min_agent/cli.py
src/min_agent/agent_loop.py
src/min_agent/context_builder.py
src/min_agent/context_loader.py
src/min_agent/deepseek_client.py
src/min_agent/deepseek_llm.py
src/min_agent/fake_llm.py
src/min_agent/tool_registry.py
src/min_agent/trace_recorder.py
src/min_agent/trace_server.py
src/min_agent/types.py
src/min_agent/tools/command.py
src/min_agent/tools/workspace.py
web/trace_viewer.html
web/trace_viewer.css
web/trace_viewer.js
tests/test_agent_loop.py
tests/test_cli.py
tests/test_cli_scenarios.py
tests/test_permission_flow.py
tests/test_trace_recorder.py
tests/test_trace_server.py
tests/test_trace_viewer_source.py
tests/test_project_structure.py
tests/test_project_testing_rules.py
```

Before editing, run and record:

```bash
git status -sb
git diff -- AGENTS.md README.md CHANGELOG.md docs/runbook.md src web tests
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

Plan-writing baseline:

- Branch: `codex/min-agent-demo-v1.0`.
- Clean V0.9 implementation baseline: `eb204766b88b3567dffe55c293aca8a615a6c077`.
- `docs/superpowers/v1.0/` is currently untracked and contains the accepted PRD and prototype; preserve both.
- Existing automated baseline: 377 tests passing.
- No V1.0 runtime implementation exists yet.
- Current `TraceServer` is per-run, serves static Viewer assets and `/events`, and shuts down after the CLI run.
- Current permission callback is synchronous and reads terminal input.

Preserve all user-owned changes. Do not use `git diff` alone to review `docs/superpowers/v1.0/`, because untracked files are not shown there; use `git status`, `rg`, `nl`, and direct file reads.

### Hard product constraints

- Start one local service without requiring a goal argument.
- Bind only to `127.0.0.1`.
- The service startup configuration fixes one workspace and one runs directory.
- The page never accepts, selects, or changes the workspace.
- The default browser page is task launch, not the Viewer.
- A run chooses exactly one decision model: `fake` or `deepseek`.
- Fake is the default and never reads or validates the DeepSeek Key.
- The Web-mode DeepSeek Key comes only from `SessionKeyStore`; it does not fall back to `DEEPSEEK_API_KEY`.
- Existing one-shot CLI DeepSeek behavior continues to read only `DEEPSEEK_API_KEY`.
- Key configuration means “present in process memory”, not “validated by a network request”.
- The Key is never written to `.env`, source, run records, TraceEvent, logs, URL, Cookie, `localStorage`, `sessionStorage`, IndexedDB, or Service Worker caches.
- The service owns at most one active run. There is no queue.
- `AgentLoop` remains the execution core and `ToolRegistry` remains the only tool execution path.
- Existing `list_dir`, `read_file`, `write_file`, and `run_command` boundaries do not change.
- Only current `write_file` and `run_command` requests can be approved or rejected in the Web page.
- A permission decision applies once to one `permission_id`; duplicate decisions cannot execute a tool twice.
- Closing a permission drawer, changing page, refreshing, or losing SSE does not approve or reject.
- Historical runs are read-only and never create a permission request or tool call.
- History provides no delete, rename, export, rerun, resume, or record mutation.
- TraceEvent and saved run records remain the only Viewer data sources.
- The V0.9 Viewer interior keeps its module order, key IDs, task-plan behavior, artifact behavior, and read-only nature.
- V1.0 adds only the outer application shell, launch/history pages, Viewer metadata, and global permission layer around that interior.
- Existing one-shot CLI flags, exit codes, terminal permission chain, Viewer behavior, and tests remain supported.
- No remote access, login, multi-user, multi-workspace, concurrent runs, queue, retry, resume, page cancel, dynamic plan editing, arbitrary command, long-term memory, multi-Agent, MCP, Hook, or plugin system.
- There is no Web control to stop the service; service shutdown remains terminal `Ctrl+C`.

### Input authority

Use the following order when documents answer different questions:

1. `product-design.md` owns product behavior, security boundary, and acceptance scope.
2. `web-agent-prototype.html` owns visible information architecture, layout, state presentation, responsive behavior, and interaction reference.
3. This plan owns implementation names, module responsibilities, API shapes, task order, and verification commands.
4. Existing V0.9 code owns behavior that the PRD explicitly preserves.

If the PRD, prototype, this plan, or current implementation conflict in a way not resolved above, stop and report the exact conflict. Do not silently choose a different behavior.

## 2. Required user-visible result

The canonical Web service command is:

```bash
PYTHONPATH=src python3 -m min_agent.web_app \
  --workspace examples/workspace \
  --runs-dir runs \
  --port 8765
```

Required service output:

```text
Workspace: <resolved workspace>
Web Agent: http://127.0.0.1:<actual-port>/
Press Ctrl+C to stop.
```

`--port 0` asks the OS for a free port. `--no-browser` prints the URL without opening it. The service stays alive after terminal run states until the user presses `Ctrl+C`.

### Canonical Fake flow

```text
GET /
-> 发起任务 is visible
-> workspace is read-only
-> Fake is selected
-> submit “请读取 notes.md 并总结”
-> POST /api/runs returns 201 and run_id
-> route changes to #/trace
-> current snapshot and SSE render the real run
-> read_file / observation_added / final_answer / run_completed
-> no task-plan panel for the simple goal
-> service returns to ready and remains available
```

### Canonical DeepSeek composite flow

```text
select DeepSeek
-> configure Key for this process
-> input is cleared and only configured=true is returned
-> submit canonical four-task goal
-> route changes to #/trace
-> plan/tasks/artifacts render through the V0.9 Viewer
-> permission_requested(run_command)
-> global “待审批 1” appears and drawer opens
-> approve
-> permission_resolved(true) before tool_started(run_command)
-> permission_requested(write_file)
-> approve
-> permission_resolved(true) before tool_started(write_file)
-> 4/4 completed and final answer displayed
-> terminal run is saved and appears in history
```

Canonical composite goal:

```text
阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。
```

### Canonical rejection flow

```text
permission_requested(write_file)
-> drawer is closed without a decision
-> permission remains pending and “待审批 1” remains visible
-> drawer is reopened
-> reject once
-> permission_resolved(approved=false)
-> observation_added(permission rejected)
-> no tool_started(write_file)
-> failed/terminal result saved to history
```

### Exact page structure

```text
Global application header
├── 发起任务
├── 过程查看
├── 历史运行
└── 待审批 1 (only while pending)

Launch page
├── fixed Workspace
├── Fake / DeepSeek model choice
├── conditional DeepSeek Key panel
├── goal input
├── start button
└── service/current-run information

Process page
├── Viewer-external run metadata
└── frozen V0.9 Viewer interior
    ├── 运行状态
    ├── 原始需求
    ├── 本次任务统计
    ├── 最终结果
    ├── 任务计划（仅复合任务）
    │   ├── 任务卡片
    │   └── 所选任务产物
    └── 执行轮次 / 轮次详情

History page
├── saved-run list
└── selected-run summary and replay entry

Global permission drawer
├── current run and tool
├── reason, workspace, target/command and preview/risk
└── reject / approve once
```

The prototype-only state control bar (`初始状态`, `运行中`, `等待审批`, `运行完成`) must not appear in production.

### Frozen Viewer IDs

The Web app and legacy CLI Viewer must keep these IDs exactly once inside their own document:

```text
#current-title
#run-status
#original-request
#run-summary
#final-answer
#task-plan-panel
#task-progress-text
#task-progress-value
#task-list
#task-artifact-panel
#task-artifact-title
#task-artifact-status
#task-artifact-body
#selected-task-label
#round-list
#round-detail
```

This frozen list is derived from the current production V0.9 implementation in `web/trace_viewer.html`, not from every identifier used by the earlier review prototype. In particular:

- production V0.9 uses `#current-title`; `docs/superpowers/v0.9/trace-viewer-prototype.html` used the prototype-only `#run-title`;
- production V0.9 uses `#final-answer`; the V0.9 prototype also used prototype-only `#final-result` and `#result-panel` identifiers;
- `#result-panel` is therefore not a frozen V0.9 ID and the shared Viewer core must not require it;
- if result-state styling needs a container, use the existing root-scoped `.result` container without renaming or adding a required legacy ID.

The V0.9 prototype remains a historical visual/product reference. The current production DOM is authoritative for legacy compatibility.

No launch, model, Key, permission, history, retry, edit, pause, cancel, or rerun control may be placed inside `[data-trace-viewer-root]`.

## 3. Target architecture

```text
Browser
├── web_agent.html / web_agent.js / web_agent.css
├── TraceViewerCore instance
├── same-origin JSON requests
└── one current-run EventSource
        │
        ▼
WebAgentServer (ThreadingHTTPServer, 127.0.0.1)
├── static asset handler
├── API validation + Origin/Host guard
├── SSE subscription adapter
├── SessionKeyStore
├── RunHistory
└── RunManager
        ├── one ManagedRun
        ├── one Agent worker thread
        ├── one TraceRecorder
        ├── one PermissionBroker
        └── existing runtime
            ├── AgentLoop
            ├── ContextBuilder / ContextLoader
            ├── FakeLLM or DeepSeekLLM
            └── ToolRegistry -> existing tools
```

### Thread ownership

| Thread | Owns | Must not do |
| --- | --- | --- |
| Main service thread | startup, shutdown, user-facing process lifecycle | run AgentLoop inline |
| HTTP request threads | short JSON/static requests, SSE connection loop | hold RunManager locks during network writes; execute tools |
| One Agent worker | one `AgentLoop.run()` | serve HTTP or read terminal input |
| Permission waiting Agent worker | waits on `threading.Condition` in `PermissionBroker.request()` | block the HTTP server |

The `PermissionBroker` wait has no arbitrary approval timeout. It ends only when the page resolves the request or service shutdown cancels the wait.

### Runtime ownership

| Object | Owner | Lifetime |
| --- | --- | --- |
| `SessionKeyStore` | Web service | process lifetime |
| `RunHistory` | Web service | process lifetime; reads saved files on demand |
| `RunManager` | Web service | process lifetime |
| `PermissionBroker` | Web service/RunManager | process lifetime, at most one pending request |
| `ManagedRun` | RunManager | current/last run in memory |
| `TraceRecorder` | ManagedRun | one run |
| Decision model | ManagedRun | one run |
| ToolRegistry | ManagedRun | one run, fixed workspace |
| `TraceViewerCore` | page | one instance for the embedded Viewer |

### Service state

```text
ready
-> busy
-> approval_required
-> busy
-> ready
```

`completed`, `failed`, and `interrupted` are run states. After any terminal run state, the service is `ready` while the last run remains available for current-process viewing.

### Run state

```text
running
├── completed
├── failed
├── interrupted
└── waiting_permission
    ├── running      (approved)
    ├── failed       (rejected and run fails)
    └── interrupted  (service shutdown)
```

There is no `queued` state. Terminal states never transition back to active.

### Permission state

```text
pending -> approved
pending -> rejected
pending -> cancelled (service shutdown only)
```

`cancelled` is internal shutdown state and must not be reported as user rejection. The corresponding run becomes `interrupted`.

## 4. Exact backend contracts

Use the names and meanings in this section consistently across Python, API JSON, tests, and frontend code.

### 4.1 Web service configuration

Define in `src/min_agent/web_app.py`:

```python
@dataclass(frozen=True)
class WebAppConfig:
    workspace: Path
    runs_dir: Path
    port: int
    open_browser: bool
    step_delay_seconds: float
    deepseek_model: str
    deepseek_base_url: str
    model_timeout_seconds: float
    model_max_tokens: int
```

Rules:

- Resolve and validate `workspace` before constructing service objects.
- Resolve `runs_dir` relative to the current process without creating it until a run is saved.
- Reject ports outside `0..65535` through `argparse`/startup validation.
- Do not include a Key field.
- Do not read `DEEPSEEK_API_KEY` in `web_app.py`, `RunManager`, or `SessionKeyStore`.

### 4.2 SessionKeyStore

Define in `src/min_agent/session_key_store.py`:

```python
class SessionKeyStore:
    def configure(self, raw_key: str) -> None: ...
    def is_configured(self) -> bool: ...
    def require(self) -> str: ...
    def clear(self) -> None: ...
```

Rules:

- Protect access with `threading.Lock`.
- Normalize once with `raw_key.strip()`.
- Reject empty or whitespace-only Key.
- Reject a normalized Key longer than 4096 characters.
- `require()` returns the Key only to backend model construction; it is never called by an API serializer.
- Do not add `to_dict`, `__repr__` output, logging, hashing, masking, prefix, suffix, persistence, or environment fallback.
- `clear()` overwrites the only stored reference with `None`.

Use typed errors:

```python
class InvalidSessionKey(ValueError): ...
class SessionKeyNotConfigured(RuntimeError): ...
```

### 4.3 PermissionBroker

Define in `src/min_agent/permission_broker.py`:

```python
PermissionStatus = Literal["pending", "approved", "rejected", "cancelled"]

@dataclass(frozen=True)
class PermissionSnapshot:
    permission_id: str
    run_id: str
    tool_name: str
    reason: str
    args: dict[str, Any]
    preview: str
    details: dict[str, Any]
    requested_at: str
    status: PermissionStatus

    def to_public_dict(self) -> dict[str, Any]: ...

class PermissionBroker:
    def request(self, run_id: str, action: AgentAction,
                details: dict[str, Any]) -> bool: ...
    def current(self) -> PermissionSnapshot | None: ...
    def resolve(self, permission_id: str, approved: bool) -> PermissionSnapshot: ...
    def cancel_pending(self) -> None: ...
```

Internal behavior:

1. `request()` creates a UUID-backed snapshot under a `threading.Condition`.
2. It rejects creation if another request is pending; this is an internal invariant failure, not a queue.
3. It publishes the `pending` snapshot under the Condition before entering the wait loop.
4. It waits in a predicate loop, never a naked `wait()` assumption.
5. `resolve()` only accepts the exact current `permission_id` and a real JSON boolean.
6. The first valid decision updates status and notifies the waiting Agent thread.
7. A repeated or stale decision raises `PermissionAlreadyResolved` or `PermissionNotFound`; it never returns a second approval.
8. `request()` returns `True` only for `approved` and `False` only for `rejected`.
9. If `cancel_pending()` changes the state to `cancelled`, `request()` raises `PermissionWaitCancelled` instead of returning `False`.
10. RunManager catches `PermissionWaitCancelled`, emits `run_interrupted`, and finalizes the record once.

Public serialization:

- `write_file`: return `path`, `mode`, and the existing 200-character `preview`; do not return duplicate full content through the permission endpoint.
- `run_command`: return `command_id` plus validated `details.command`, `details.workspace`, and `details.risk`.
- Return only JSON-safe copies.
- Permission data never includes a model Key.

### 4.4 Managed run

Define in `src/min_agent/run_manager.py`:

```python
DecisionModelName = Literal["fake", "deepseek"]
ManagedRunStatus = Literal[
    "running", "waiting_permission", "completed", "failed", "interrupted"
]

@dataclass
class ManagedRun:
    run_id: str
    user_goal: str
    workspace: str
    decision_model: DecisionModelName
    status: ManagedRunStatus
    created_at: str
    finished_at: str | None
    result: AgentRunResult | None
    recorder: TraceRecorder
    thread: threading.Thread | None
    record_path: Path | None
    finalized: bool

    def to_public_dict(self, include_events: bool = True) -> dict[str, Any]: ...
```

`RunManager` public contract:

```python
class RunManager:
    def start_run(self, goal: str, decision_model: str) -> dict[str, Any]: ...
    def service_state(self) -> str: ...
    def current_snapshot(self, include_events: bool = True) -> dict[str, Any] | None: ...
    def active_run_id(self) -> str | None: ...
    def has_active_deepseek_run(self) -> bool: ...
    def subscribe(self, run_id: str) -> RunEventSubscription: ...
    def close(self) -> None: ...
```

Exact event-subscription contract:

```python
@dataclass
class RunEventSubscription:
    run_id: str
    initial_events: list[TraceEvent]
    event_queue: queue.Queue[TraceEvent | None]
    close_callback: Callable[[], None]

    def close(self) -> None: ...
```

RunManager registers one recorder broadcast subscriber per ManagedRun. `subscribe()` adds the new queue to a manager-owned subscription set before reading `recorder.history()`. An event that lands in both initial history and the live queue is an allowed duplicate; an event gap is not allowed. `close()` removes the queue idempotently. Finalization and service shutdown put one `None` sentinel into every remaining queue.

Exact public run snapshot:

```json
{
  "run_id": "...",
  "user_goal": "...",
  "workspace": "/resolved/workspace",
  "decision_model": "fake",
  "status": "running",
  "active": true,
  "created_at": "...",
  "finished_at": null,
  "result": null,
  "events": []
}
```

Terminal `result` contains only `AgentRunResult.to_dict()`. Public snapshots never serialize the worker thread, recorder object, subscriber queues, raw DeepSeek Key, internal exception, or record filesystem path.

Validation:

- Normalize `goal` with `.strip()`.
- Reject empty goal and goal length over 1000.
- Accept only exact `fake` or `deepseek`.
- Check active-run conflict while holding the manager lock.
- For DeepSeek, call `SessionKeyStore.require()` only after winning the active-run check.
- Create the recorder and ManagedRun before starting the worker so the API never returns an unowned run ID.
- Return the snapshot only after `thread.start()` succeeds.
- If thread startup fails, finalize a failed record and return a server error; do not leave an active run.

Worker construction:

- One new `ToolRegistry` per run, using the fixed workspace.
- One new `ContextLoader`, `ContextBuilder`, and decision model per run.
- Fake uses `FakeLLM()` without touching Key Store.
- DeepSeek uses a one-time backend read of the in-memory Key to construct `DeepSeekClient` and `DeepSeekLLM`.
- Permission callback is `lambda action, details: broker.request(run_id, action, details)`.
- Model/tool failures become the existing `AgentRunResult`/Trace failure path and do not stop the Web server.

State derivation:

- A recorder subscriber changes run state to `waiting_permission` on `permission_requested`.
- It changes back to `running` on `permission_resolved(approved=true)`.
- User rejection follows existing AgentLoop events and final result; do not invent a frontend terminal state.
- Final state comes from the actual `AgentRunResult` or interruption handling.
- `_finalize_run()` is lock-protected and idempotent: exactly one terminal state, `finished_at`, record save, and subscription close.

Shutdown:

- Mark the manager closing before accepting more runs.
- Call `PermissionBroker.cancel_pending()`.
- Wait at most 2 seconds for the worker.
- If still active, emit one `run_interrupted` event and save `interrupted` through idempotent finalization.
- The worker is daemonized so a stuck external model request cannot keep the process alive.
- A late worker return after finalization cannot overwrite the interrupted state or save a second terminal record.

### 4.5 Run record and history contract

Extend `TraceRecorder` with optional `decision_model` metadata and pass it from both CLI and Web entry points.

New records use:

```json
{
  "run_id": "...",
  "status": "completed",
  "user_goal": "...",
  "workspace": "/resolved/workspace",
  "decision_model": "fake",
  "started_at": "...",
  "ended_at": "...",
  "events": []
}
```

Preserve existing `started_at` and `ended_at` keys. In Web API snapshots:

- `created_at` maps to record `started_at`.
- `finished_at` maps to record `ended_at`.

Do not rename or remove existing keys. Existing pre-V1.0 records without `decision_model` load as `"unknown"`; do not infer a model from free-form event text.

Define `RunHistory` in `src/min_agent/run_history.py`:

```python
@dataclass(frozen=True)
class HistoryListResult:
    runs: list[dict[str, Any]]
    load_error_count: int

    def to_dict(self) -> dict[str, Any]: ...

class RunHistory:
    def list_runs(self) -> HistoryListResult: ...
    def load_run(self, run_id: str) -> dict[str, Any]: ...
```

Rules:

- Only accept run IDs matching `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`.
- Resolve `<runs_dir>/<run_id>.json` and require it to remain inside `runs_dir`.
- Read UTF-8 JSON with a bounded maximum file size of 10 MiB.
- Validate top-level object, run ID match, status, goal, timestamps, and `events` list.
- Validate every event belongs to the requested `run_id` and has an integer step.
- Sort list results by `started_at` descending, then run ID descending for stable ties.
- Isolate malformed records. `list_runs()` returns valid entries plus a non-secret `load_error_count`; do not fail the page because one file is corrupt.
- `load_run()` returns not found for corrupt or missing requested records with an explicit typed error.
- History reading never executes, resumes, modifies, or saves a run.
- Do not expose arbitrary files from `runs_dir`.

History summaries include:

```json
{
  "run_id": "...",
  "goal": "...",
  "decision_model": "fake|deepseek|unknown",
  "status": "completed|failed|interrupted",
  "created_at": "...",
  "finished_at": "...",
  "completed_tasks": 4,
  "total_tasks": 4,
  "final_answer": "..."
}
```

Derive task counts and final answer only from structured events.

### 4.6 HTTP response envelope

All JSON responses use UTF-8 and `application/json; charset=utf-8`.

Success:

```json
{"ok": true, "data": {}}
```

Failure:

```json
{
  "ok": false,
  "error": {
    "code": "active_run_conflict",
    "message": "已有任务正在运行，请进入过程查看。"
  }
}
```

Never place a Python traceback, exception repr, request body, Key fragment, or filesystem content in an API error.

### 4.7 Exact HTTP routes

| Method | Route | Success | Main failures |
| --- | --- | --- | --- |
| GET | `/` | `web_agent.html` | 404 if asset missing |
| GET | `/api/state` | service config/status, current snapshot, configured boolean | 500 sanitized |
| PUT | `/api/deepseek-key` | `configured=true` | 400 invalid; 409 active DeepSeek run |
| DELETE | `/api/deepseek-key` | `configured=false` | 409 active DeepSeek run |
| POST | `/api/runs` | 201 with run snapshot | 400 input; 409 active run/key missing |
| GET | `/api/runs/current` | current/last in-memory snapshot or null | 500 sanitized |
| GET | `/api/runs/current/events?run_id=<id>` | SSE for exact current/last in-memory run | 400/404/409 |
| GET | `/api/permissions/current` | current pending snapshot or null | 500 sanitized |
| POST | `/api/permissions/<permission_id>/decision` | resolved status | 400 boolean; 404 stale; 409 already resolved |
| GET | `/api/history` | valid summaries and load error count | 500 sanitized |
| GET | `/api/history/<run_id>` | one validated full record | 400 invalid ID; 404 missing/corrupt |

Exact request bodies:

```json
PUT /api/deepseek-key
{"api_key": "<secret>"}
```

```json
POST /api/runs
{"goal": "请读取 notes.md 并总结", "decision_model": "fake"}
```

```json
POST /api/permissions/<permission_id>/decision
{"approved": true}
```

`POST /api/runs` must reject unknown fields that could expand authority, especially `workspace`, `runs_dir`, `command`, `base_url`, or arbitrary model names. Do not silently honor them.

`GET /api/state` data:

```json
{
  "service_status": "ready|busy|approval_required",
  "workspace": "/resolved/workspace",
  "deepseek_key_configured": false,
  "current_run": null
}
```

The current snapshot may be terminal. `service_status` is still `ready` when the snapshot is terminal.

### 4.8 Host, Origin, body, and static security

- Server socket binds only `("127.0.0.1", port)`.
- Published origin is exactly `http://127.0.0.1:<actual-port>`.
- Every request validates `Host` equals `127.0.0.1:<actual-port>`.
- State-changing `PUT`, `POST`, and `DELETE` requests require `Origin` exactly equal to the published origin.
- Do not enable CORS or return `Access-Control-Allow-Origin`.
- Reject unsupported methods with 405.
- Require `Content-Type: application/json` for JSON mutations.
- Reject missing, invalid, non-object, or trailing JSON.
- Reject request bodies over 16 KiB before reading them fully.
- Normalize static `/` to `web_agent.html`.
- Static asset resolution stays under the configured `web` directory.
- Serve only regular files with known MIME type fallback.
- Do not expose directory listings, source directories, run records, `.git`, or arbitrary paths.
- Suppress default HTTP request logging because mutation paths and sizes are enough operational context; never log bodies.

### 4.9 SSE contract

The only live stream is the exact current/last in-memory run requested by run ID:

```text
GET /api/runs/current/events?run_id=<exact-run-id>
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

Rules:

- Subscribe before taking recorder history so no event gap occurs; duplicate history/queue events are allowed at transport level and deduplicated by `(run_id, step)` in the client.
- Send existing history first, then new events.
- Every event is existing `TraceEvent.to_dict()` JSON.
- Reject a run ID that is not the in-memory current/last run.
- Send no events from another run.
- Close the stream after the requested run becomes terminal and its final event has been sent.
- Remove disconnected queues in `finally`.
- Broken pipe/reset is normal and does not fail the run.
- Service shutdown sends a sentinel to every stream.
- Do not create a separate Web event schema.

### 4.10 Shared Viewer browser contract

Define `window.MinAgentTraceViewer` in `web/trace_viewer_core.js`:

```javascript
const viewer = window.MinAgentTraceViewer.create({ root });
viewer.loadRun({ runId, status, events });
viewer.applyEvent(event);
viewer.setConnectionStatus("connected|reconnecting|unsupported");
viewer.reset();
viewer.destroy();
```

Rules:

- All prior render/state functions move to the core with behavior preserved.
- State is instance-owned, not one global singleton.
- Every query is scoped to `root`.
- `loadRun()` clears prior run selection and derives all visible state from the supplied events.
- `applyEvent()` rejects an event with another run ID.
- Dedupe by `(run_id, step)` and keep ascending step order.
- Historical `loadRun()` never opens EventSource.
- Core contains no fetch, URL routing, Key, permission decision, launch, or history-list logic.
- `web/trace_viewer.js` becomes only the legacy `/events` connection wrapper.
- Existing CLI `trace_viewer.html` loads core first and wrapper second.
- Web Agent loads the same core and feeds it API snapshot/SSE events.
- Do not duplicate the 1300-line renderer into `web_agent.js`.

## 5. File responsibility map

### Modify before runtime work

- `AGENTS.md`: add V1.0 boundary, Web security, single-active-run, Key, permission, Viewer reuse, and testing rules before implementation code.

### New backend files

- `src/min_agent/runtime_factory.py`: shared fixed-workspace ToolRegistry construction and explicit CLI/Web decision-model construction helpers.
- `src/min_agent/session_key_store.py`: process-memory Key ownership only.
- `src/min_agent/permission_broker.py`: condition-based one-pending-request bridge.
- `src/min_agent/run_history.py`: safe run-record list/load and summaries.
- `src/min_agent/run_manager.py`: one active background run, state, subscriptions, finalization, shutdown.
- `src/min_agent/web_server.py`: long-running local static/JSON/SSE HTTP server and request security.
- `src/min_agent/web_app.py`: CLI parsing, service composition, browser open, signal/KeyboardInterrupt shutdown.

### Modified backend files

- `src/min_agent/cli.py`: import shared registry factory, pass decision model metadata, otherwise preserve behavior.
- `src/min_agent/trace_recorder.py`: optional decision model metadata and safe run-record snapshot used by manager/history tests.
- `src/min_agent/types.py`: only if a shared type alias is genuinely used by more than one module; do not move Web-only transport types into the Agent domain by default.
- `src/min_agent/agent_loop.py`: no planned feature change. Modify only if a focused test proves cancellation cannot propagate safely through the existing callback boundary; do not redesign the loop.
- `src/min_agent/trace_server.py`: preserve legacy server contract. Reuse generic ideas, but do not turn the one-shot server into the V1.0 coordinator.

### New Web files

- `web/trace_viewer_core.js`: shared Viewer state and rendering.
- `web/web_agent.html`: production three-page shell, embedded frozen Viewer DOM, permission drawer.
- `web/web_agent.css`: outer shell, launch/history/permission/responsive styles from the accepted prototype.
- `web/web_agent.js`: API, hash routing, current-run stream, Key UI, permission UI, history replay, focus and reconnect state.

### Modified Web files

- `web/trace_viewer.html`: add only a root marker and core script before the legacy wrapper; interior order/IDs unchanged.
- `web/trace_viewer.js`: retain only legacy SSE bootstrap and delegate rendering to the core.
- `web/trace_viewer.css`: remain the shared Viewer interior stylesheet; scope any formerly global selector needed for safe embedding without visual redesign.

### New tests

- `tests/test_runtime_factory.py`
- `tests/test_session_key_store.py`
- `tests/test_permission_broker.py`
- `tests/test_run_history.py`
- `tests/test_run_manager.py`
- `tests/test_web_server.py`
- `tests/test_web_app.py`
- `tests/test_web_agent_source.py`
- `tests/test_web_scenarios.py`

### Modified tests

- `tests/test_cli.py`
- `tests/test_cli_scenarios.py`
- `tests/test_trace_recorder.py`
- `tests/test_trace_server.py` only for explicit legacy non-regression.
- `tests/test_trace_viewer_source.py`: read core plus wrapper where responsibilities moved; preserve behavioral assertions.
- `tests/test_project_structure.py`
- `tests/test_project_testing_rules.py`

### User-facing documentation after implementation

- `README.md`: V1.0 service command, Fake/DeepSeek launch flow, session-Key boundary, and legacy CLI compatibility.
- `docs/runbook.md`: service operation, API-free user flow, permission scenarios, history, test commands, browser evidence, and cleanup.
- `CHANGELOG.md`: V1.0 user-visible change, explicit non-goals, completion evidence, and browser result.

No other file is in scope unless a failing test proves a direct requirement. Stop and explain before broadening the file map.

## Task 1: Freeze V1.0 rules and extend run-record metadata

**Files:**

- Modify: `AGENTS.md`
- Modify: `src/min_agent/trace_recorder.py`
- Modify: `src/min_agent/cli.py`
- Modify: `tests/test_trace_recorder.py`
- Modify: `tests/test_project_testing_rules.py`
- Modify: `tests/test_cli_scenarios.py`

- [ ] **Step 1: Add the V1.0 rule section before runtime implementation**

Place the new rule after V0.9. It must state plainly:

```md
## V1.0 边界

V1.0 只增加一个本机长驻 Web Agent 操作闭环：网页发起 Fake/DeepSeek 任务、网页处理当前运行的危险工具权限、复用 V0.9 Viewer 查看过程，以及只读历史回放。

V1.0 不改变 AgentLoop、ToolRegistry、任务计划、任务产物、workspace、write_file 或 run_command 的既有安全边界。

## V1.0 Web Agent 规则

- 服务只监听 127.0.0.1，workspace 由启动参数固定，页面不能传入或切换 workspace。
- 同一时间最多一个活动运行，不排队、不并发。
- Web 模式的 DeepSeek Key 只存于服务进程内存，不读写 .env，不进入日志、Trace、run record 或浏览器持久化存储；Fake 不读取 Key。
- 网页只能处理当前运行产生的 write_file 和 run_command 权限；关闭抽屉不等于拒绝；一份权限只能处理一次。
- 历史回放只读，不能产生权限或工具执行。
- V0.9 Viewer 内部模块顺序、关键 ID、任务产物和轮次交互保持不变；V1.0 页面能力放在 Viewer 外层。
- 现有单次 CLI 入口和终端权限确认继续兼容。
```

Update the testing section to require:

- Web API unit tests use standard-library local HTTP clients.
- Web page changes require real browser acceptance.
- Source structure tests cannot be reported as browser PASS.
- Key leak scans are part of V1.0 acceptance.

- [ ] **Step 2: Write failing metadata tests**

Add tests proving:

```python
recorder = TraceRecorder(
    user_goal="goal",
    workspace="workspace",
    run_id="run-1",
    decision_model="fake",
)
path = recorder.save(runs_dir, status="completed")
data = json.loads(path.read_text())
self.assertEqual(data["decision_model"], "fake")
self.assertIn("started_at", data)
self.assertIn("ended_at", data)
```

Also prove `decision_model=None` is accepted for old direct test construction and serializes as `"unknown"`, not a missing key.

Add a CLI scenario assertion that a newly saved Fake record contains `decision_model="fake"`. Do not assert an exact timestamp or generated run ID.

- [ ] **Step 3: Run RED tests**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_trace_recorder \
  tests.test_project_testing_rules \
  tests.test_cli_scenarios
```

Expected RED: constructor/save output and V1.0 rule assertions fail for the missing contract.

- [ ] **Step 4: Implement the minimal record change**

- Add an optional `decision_model: str | None = None` parameter to `TraceRecorder` after existing compatible parameters.
- Store only normalized known values `fake`, `deepseek`, or `unknown`.
- Include `decision_model` in saved JSON.
- Pass `args.decision_model` from the existing CLI.
- Do not rename `started_at`, `ended_at`, `events`, or file naming.
- Do not put Key data or model configuration into TraceEvent.

- [ ] **Step 5: Run GREEN tests and regression slice**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_trace_recorder \
  tests.test_project_testing_rules \
  tests.test_cli \
  tests.test_cli_scenarios
```

Expected: PASS, with existing negative-path CLI prints allowed only when unittest exits 0 and summary is OK.

## Task 2: Extract shared runtime factories without changing CLI behavior

**Files:**

- Create: `src/min_agent/runtime_factory.py`
- Modify: `src/min_agent/cli.py`
- Create: `tests/test_runtime_factory.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_cli_scenarios.py`

- [ ] **Step 1: Write failing factory parity tests**

Test exact registry behavior:

- `read_file` and `list_dir` are permission-free.
- `write_file` and `run_command` require permission.
- `run_command` still uses the default fixed command registry and rejects an unknown `command_id` before permission.
- All tools remain scoped to the provided workspace.

Test decision models:

```python
model, error = build_web_decision_model(
    "fake",
    api_key=None,
    deepseek_model="deepseek-v4-flash",
    deepseek_base_url="https://api.deepseek.com",
    model_timeout_seconds=30.0,
    model_max_tokens=1200,
)
self.assertIsInstance(model, FakeLLM)
self.assertIsNone(error)
```

For DeepSeek, test missing Key fails before a client is returned and a provided fake Key is held only inside the client object used by that run. Do not print or snapshot it.

- [ ] **Step 2: Run RED tests**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_runtime_factory
```

Expected RED: `min_agent.runtime_factory` does not exist.

- [ ] **Step 3: Move, do not duplicate, shared construction**

Implement:

```python
def build_tool_registry(workspace: Path) -> ToolRegistry: ...

def build_web_decision_model(
    decision_model: str,
    *,
    api_key: str | None,
    deepseek_model: str,
    deepseek_base_url: str,
    model_timeout_seconds: float,
    model_max_tokens: int,
) -> tuple[DecisionModel | None, str | None]: ...
```

Rules:

- Move the existing ToolRegistry setup byte-for-byte in behavior.
- `build_web_decision_model("fake", ...)` must return before inspecting `api_key`.
- `build_web_decision_model("deepseek", ...)` requires the explicitly passed Key; never read environment variables.
- Preserve `cli.build_tool_registry` as an imported compatibility name because current tests and possible users import it.
- Preserve `cli.build_decision_model(args)` and its `DEEPSEEK_API_KEY` behavior as the CLI-only wrapper.
- Do not make `runtime_factory` import `cli` or Web modules.

- [ ] **Step 4: Run GREEN and CLI regression**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_runtime_factory \
  tests.test_cli \
  tests.test_cli_scenarios \
  tests.test_command_registry \
  tests.test_tool_registry
```

Expected: PASS and no CLI command or permission difference.

## Task 3: Add the process-memory SessionKeyStore

**Files:**

- Create: `src/min_agent/session_key_store.py`
- Create: `tests/test_session_key_store.py`
- Modify: `tests/test_project_structure.py`

- [ ] **Step 1: Write failing Key lifecycle tests**

Cover:

- initial `is_configured()` is false;
- configure/require returns the exact normalized Key to backend code;
- whitespace-only and over-4096 input fails without changing an existing Key;
- reconfiguration replaces the in-memory value;
- clear makes `require()` raise `SessionKeyNotConfigured`;
- concurrent configure/read/clear never returns a partially updated value;
- no `to_dict`, serialization, file write, environment access, or logging method exists.

Do not use a real Key. Use a sentinel such as `test-secret-never-log` and ensure the test does not print it.

- [ ] **Step 2: Run RED**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_session_key_store
```

Expected RED: module missing.

- [ ] **Step 3: Implement the smallest lock-protected store**

Use one private `str | None` and one `threading.Lock`. No TTL, encryption wrapper, keyring, file, cache, observer, global singleton, or validation network request.

When invalid input is supplied, validate before replacing the stored value so a previously valid Key remains configured.

- [ ] **Step 4: Run GREEN and source leak guard**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_session_key_store \
  tests.test_project_structure
```

Then inspect:

```bash
rg -n "DEEPSEEK_API_KEY|localStorage|sessionStorage|\.env" \
  src/min_agent/session_key_store.py tests/test_session_key_store.py
```

Expected: no environment or browser persistence implementation in the store. A test name may mention a prohibited term only when asserting absence.

## Task 4: Add the condition-based PermissionBroker

**Files:**

- Create: `src/min_agent/permission_broker.py`
- Create: `tests/test_permission_broker.py`
- Modify: `tests/test_project_structure.py`

- [ ] **Step 1: Write deterministic threaded tests**

Use `threading.Event` for test coordination; do not use arbitrary sleeps as proof.

Required tests:

1. `request()` publishes one pending snapshot and blocks the requester thread.
2. `resolve(id, True)` unblocks and returns `True` exactly once.
3. `resolve(id, False)` unblocks and returns `False` exactly once.
4. Closing/reading `current()` does not resolve anything.
5. Wrong ID is rejected and the original request remains pending.
6. Second pending request is rejected.
7. Duplicate decision cannot return a second approval.
8. `cancel_pending()` raises `PermissionWaitCancelled` in the requester thread.
9. Public `write_file` snapshot contains path/mode/preview but not duplicate full content.
10. Public `run_command` snapshot contains validated command details.
11. Snapshots are defensive copies; caller mutation cannot change broker state.

- [ ] **Step 2: Run RED**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_permission_broker
```

Expected RED: module missing.

- [ ] **Step 3: Implement broker state under one Condition**

Do not poll. Use:

```python
with self._condition:
    self._condition.wait_for(lambda: request.status != "pending")
```

Publish immutable snapshots outside callers' control. Preserve the raw `AgentAction` only as private internal data required to return the boolean; the API sees `to_public_dict()` only.

Do not emit TraceEvent in the broker. `AgentLoop` already emits `permission_requested` and `permission_resolved`; RunManager only derives service state.

- [ ] **Step 4: Run GREEN and repeat to expose races**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_permission_broker
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_permission_broker
```

Both runs must pass without sleep-dependent flakes or leaked threads.

## Task 5: Add safe run-history reading and summaries

**Files:**

- Create: `src/min_agent/run_history.py`
- Create: `tests/test_run_history.py`
- Modify: `tests/test_project_structure.py`

- [ ] **Step 1: Write failing history contract tests**

Use `tempfile.TemporaryDirectory()` and hand-written small JSON fixtures.

Required cases:

- list valid records newest first;
- stable order for equal timestamps;
- load a full valid record;
- map `started_at/ended_at` to `created_at/finished_at` in public data;
- derive final answer only from `final_answer` event output;
- derive total/completed task counts from `plan_created` and `task_completed` events;
- old record without `decision_model` returns `unknown`;
- one corrupt file increments `load_error_count` but does not hide valid rows;
- top-level array, missing event list, run ID mismatch, noninteger step, and cross-run event are rejected;
- `../`, absolute path, URL encoding tricks, overly long ID, symlink escape, and non-JSON file cannot be loaded;
- file over 10 MiB is rejected before JSON parsing;
- list/load never modifies file timestamps or contents.

- [ ] **Step 2: Run RED**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_run_history
```

- [ ] **Step 3: Implement validation before presentation**

Keep two representations separate:

- validated full record for Viewer replay;
- derived summary for history list.

Do not return a partially trusted corrupt record. Do not evaluate arbitrary JSON fields as HTML or commands.

- [ ] **Step 4: Run GREEN**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_run_history \
  tests.test_trace_recorder
```

## Task 6: Implement the single-active-run RunManager

**Files:**

- Create: `src/min_agent/run_manager.py`
- Create: `tests/test_run_manager.py`
- Modify: `tests/test_permission_flow.py`
- Modify: `tests/test_project_structure.py`

- [ ] **Step 1: Build controllable test doubles**

Inject factories rather than patch global modules:

```python
RunManager(
    workspace=workspace,
    runs_dir=runs_dir,
    key_store=key_store,
    permission_broker=broker,
    decision_model_factory=...,
    tool_registry_factory=...,
    context_builder_factory=...,
    step_delay_seconds=0,
)
```

Production defaults use existing real factories. Tests use DecisionModels that stop at controlled Events.

- [ ] **Step 2: Write failing lifecycle tests**

Cover:

- valid Fake start returns one `run_id` and worker starts;
- Fake start succeeds when Key Store `require()` would raise, proving it is never read;
- DeepSeek start fails before thread creation when Key is absent;
- DeepSeek reads the configured Key exactly once during run construction;
- unknown model, empty goal, whitespace goal, and over-1000 goal fail;
- active run rejects a second start atomically under concurrent calls;
- first terminal run allows a second run with a different ID;
- events and snapshots contain only their own run ID;
- `permission_requested` changes service state to `approval_required`;
- approval returns state to busy before tool execution continues;
- rejection produces existing AgentLoop denial chain and no `tool_started`;
- successful and failed runs save exactly once with decision model metadata;
- model exception becomes failed record and service returns ready;
- `close()` cancels a pending permission as interrupted, not rejected;
- late worker completion cannot overwrite interrupted finalization;
- subscriber is closed after terminal event and does not receive later run events.

Use condition/event waits with explicit maximum test time only as a deadlock guard, not as state synchronization.

- [ ] **Step 3: Run RED**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_run_manager
```

- [ ] **Step 4: Implement lock scopes and finalization**

Required lock discipline:

- Hold manager lock only while reading/updating manager-owned references and scalar state.
- Do not hold it while calling model, AgentLoop, tools, recorder subscribers, file save, queue put, or thread join.
- Use a separate per-run finalization guard or the manager lock with an immediate state mutation before I/O.
- Never call a callback while holding a Condition/manager lock if that callback can reenter manager state.

Run startup sequence:

```text
validate request
-> reserve active ManagedRun under lock
-> construct recorder/runtime
-> subscribe state/stream handlers
-> start worker
-> return public snapshot
```

Worker sequence:

```text
AgentLoop.run(goal)
-> choose completed/failed from AgentRunResult.success
-> idempotent finalize
-> save record
-> close SSE subscriptions
-> service ready
```

Exception sequence:

```text
PermissionWaitCancelled -> interrupted
other unexpected worker exception -> sanitized failed event/result
-> idempotent finalize
```

Do not return traceback text to page or final answer.

- [ ] **Step 5: Run GREEN and mechanism regression**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_run_manager \
  tests.test_agent_loop \
  tests.test_permission_flow \
  tests.test_cli_scenarios
```

Expected: all V0.1-V0.9 Agent paths remain green.

## Task 7: Implement the local WebAgentServer, JSON APIs, and run-scoped SSE

**Files:**

- Create: `src/min_agent/web_server.py`
- Create: `tests/test_web_server.py`
- Modify: `tests/test_project_structure.py`

- [ ] **Step 1: Create an HTTP test harness using only the standard library**

Start the server on port 0 with injected fake manager/history/key-store objects. Use `http.client.HTTPConnection` and always close response/server resources in test cleanup.

The harness must expose the actual server origin so mutation tests send:

```python
headers = {
    "Host": f"127.0.0.1:{port}",
    "Origin": f"http://127.0.0.1:{port}",
    "Content-Type": "application/json",
}
```

- [ ] **Step 2: Write failing static and general API tests**

Cover:

- server address is `127.0.0.1`, never `0.0.0.0`;
- `/` serves `web_agent.html` non-empty with correct MIME;
- known CSS/JS assets load;
- `..`, encoded traversal, directory path, and missing asset return 404;
- `/api/state` uses the success envelope and exposes resolved workspace, service state, configured boolean, current snapshot;
- unsupported methods return 405 JSON for API routes;
- default request log is suppressed;
- API exceptions return sanitized JSON without traceback, request body, or Key.

- [ ] **Step 3: Write failing Host/Origin/body tests**

Cover:

- missing, wrong, `localhost`, suffix/prefix-confused, and attacker Host are rejected;
- GET accepts no Origin when Host is exact;
- mutations reject missing or wrong Origin;
- no response includes CORS allowance;
- missing/wrong Content-Type fails;
- missing/invalid/scalar/list/trailing JSON fails;
- negative, absent, nonnumeric, and over-16-KiB Content-Length fail safely;
- error messages never echo body values.

The published browser URL is `127.0.0.1`, so `localhost` is intentionally not a second trusted origin in V1.0.

- [ ] **Step 4: Write failing Key API tests**

Cover:

- PUT configures and returns only `{"configured": true}`;
- response JSON contains no raw, masked, hashed, prefix, suffix, or length-derived Key information;
- input is not present in captured stdout/stderr;
- DELETE clears and returns only `{"configured": false}`;
- invalid input is 400 and does not replace prior valid Key;
- an active DeepSeek run makes PUT/DELETE return 409;
- an active Fake run does not prevent configuration for a future run;
- GET state reveals only configured boolean.

- [ ] **Step 5: Write failing run and permission API tests**

Cover exact contracts:

- valid POST run returns 201 and manager snapshot;
- blank/long goal, unknown model, extra `workspace`, extra authority fields, and non-object body return 400;
- active run and missing DeepSeek Key return 409 with distinct codes;
- GET current returns null or snapshot;
- GET current permission returns null or public pending snapshot;
- decision accepts only JSON boolean, exact ID, and current pending request;
- approval/rejection response is terminal for that permission;
- duplicate decision returns 409 and manager/broker receives one resolve call;
- stale/invalid ID returns 404/400 without changing pending request;
- history list and full record delegate to validated `RunHistory`;
- invalid history ID never reaches filesystem load.

- [ ] **Step 6: Write failing SSE tests**

Use a fake subscription with controlled `queue.Queue`:

- wrong/missing run ID is rejected;
- initial events are sent in order;
- a new queued event is sent;
- only the requested run ID appears;
- terminal event closes the stream;
- disconnected client unregisters the subscription;
- server stop closes a waiting stream;
- duplicate initial/live step is transport-valid and not rewritten;
- no custom event fields are introduced.

Do not assert success from source inspection; read actual HTTP bytes.

- [ ] **Step 7: Run RED**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_web_server
```

- [ ] **Step 8: Implement a routed Handler with injected services**

Define:

```python
class WebAgentHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False

class WebAgentServer:
    @property
    def origin(self) -> str: ...
    @property
    def url(self) -> str: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...
```

Keep route decoding explicit. Do not use substring matching such as `path.startswith("/api/history")` without validating the remaining segment.

Write response helpers for JSON, error, static, and SSE. Do not hold manager locks while writing HTTP bodies.

- [ ] **Step 9: Run GREEN twice and trace-server regression**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_web_server \
  tests.test_trace_server
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_web_server
```

Both runs must finish without hanging server threads or occupied ports.

## Task 8: Add the long-running Web service CLI entry

**Files:**

- Create: `src/min_agent/web_app.py`
- Create: `tests/test_web_app.py`
- Modify: `tests/test_project_structure.py`

- [ ] **Step 1: Write failing parser and startup tests**

Required parser options:

```text
--workspace            default examples/workspace
--runs-dir             default runs
--port                 default 8765, 0 allowed
--no-browser
--step-delay           default 0.4
--deepseek-model       default deepseek-v4-flash
--deepseek-base-url    default https://api.deepseek.com
--model-timeout        default 30.0
--model-max-tokens     default 1200
```

There is no positional goal and no `--decision-model`; model choice is per Web run.

Test:

- missing workspace returns exit 2 before server construction;
- workspace file returns exit 2;
- invalid port/config returns exit 2;
- port bind failure returns exit 2;
- static resource setup failure returns exit 2;
- successful start prints resolved workspace and exact `127.0.0.1` URL;
- browser opens only after server start and not with `--no-browser`;
- failed browser open prints manual URL but service remains usable;
- KeyboardInterrupt calls manager close, broker cancellation through manager, server close, and Key clear;
- shutdown functions are idempotent;
- Web startup does not read or require `DEEPSEEK_API_KEY`, even when absent or set;
- no startup log prints environment values.

Mock long-running wait with an injected event/function; tests must not really block awaiting Ctrl+C.

- [ ] **Step 2: Run RED**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_web_app
```

- [ ] **Step 3: Compose, do not reimplement, service objects**

Construction order:

```text
parse args
-> ensure_workspace
-> create SessionKeyStore
-> create PermissionBroker
-> create RunHistory
-> create RunManager
-> create WebAgentServer
-> start server
-> print URL
-> optionally open browser
-> wait until KeyboardInterrupt
-> manager.close
-> server.close
-> key_store.clear
```

If construction fails after an earlier resource exists, close only resources that were actually created. Avoid a shutdown exception masking the startup error.

Do not add signal handling beyond what is necessary for normal `KeyboardInterrupt`; no daemon manager, launch agent, PID file, or background service installation.

- [ ] **Step 4: Run GREEN and verify help**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_web_app \
  tests.test_cli
PYTHONPATH=src python3 -m min_agent.web_app --help
```

The help command must exit 0, list Web service options, and require no Key or network.

## Task 9: Extract one reusable Trace Viewer core without V0.9 regression

**Files:**

- Create: `web/trace_viewer_core.js`
- Modify: `web/trace_viewer.js`
- Modify: `web/trace_viewer.html`
- Modify: `web/trace_viewer.css`
- Modify: `tests/test_trace_viewer_source.py`
- Create: `tests/test_web_agent_source.py` with the core-only assertions used by later tasks

- [ ] **Step 1: Record the frozen DOM and renderer behavior in tests**

Before moving code, add/retain assertions that prove:

- the 16 frozen IDs exist exactly once;
- module order is status -> original request -> summary -> final result -> task plan -> rounds/detail;
- `#task-artifact-panel` remains inside `#task-plan-panel`;
- `#selected-task-label` remains in the rounds panel;
- simple runs hide the whole task-plan panel;
- artifact content/evidence/inheritance/flow still derives from Trace events;
- permission events do not start Agentic Loop rounds;
- denied tools are not rendered as started commands;
- the Viewer has no approve/reject/input controls;
- existing context/model/tool/command render functions remain covered after relocation.

Add a structural assertion that `trace_viewer.html` loads:

```html
<script src="./trace_viewer_core.js"></script>
<script src="./trace_viewer.js"></script>
```

in that order.

- [ ] **Step 2: Run the existing Viewer tests before refactor**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_trace_viewer_source
```

Expected: PASS before changes. This is the behavioral baseline, not RED.

- [ ] **Step 3: Record a real pre-refactor legacy Viewer browser baseline**

Before changing any Viewer HTML/CSS/JavaScript, use a dedicated temporary workspace and run the canonical Fake four-task goal through the existing one-shot CLI and existing `TraceServer`:

```bash
PYTHONPATH=src python3 -m min_agent.cli \
  "阅读 workspace 中的项目资料，获取当前时间，并生成一份带时间的 summary.md。" \
  --workspace /private/tmp/min-agent-v1-viewer-baseline-<id>/workspace \
  --runs-dir /private/tmp/min-agent-v1-viewer-baseline-<id>/runs \
  --port 0 \
  --keep-open-seconds 60 \
  --step-delay 0
```

Approve both CLI permission prompts. In a real browser, record these baseline checkpoints:

- page is nonblank and Console has no JavaScript error;
- frozen module order and 16 production IDs are present;
- task plan reaches 4/4 with four completed task cards;
- selecting each task switches its artifact content, evidence, inherited sources, and downstream flow;
- selected-task filtering updates execution rounds without moving `#selected-task-label`;
- round-detail Context Build, model decision, command, permission, tool, artifact, and terminal rendering are usable;
- final result and run status match the saved run record;
- 390px layout has no document-level horizontal overflow.

Record this as `legacy Viewer pre-refactor baseline: PASS` with the run ID and temporary workspace path. Do not delete the temporary directory without user authorization. If this baseline already fails before refactoring, stop and diagnose the existing failure rather than attributing it to the core extraction.

- [ ] **Step 4: Add failing shared-core contract assertions**

Assert core exposes `window.MinAgentTraceViewer.create`, `loadRun`, `applyEvent`, `setConnectionStatus`, `reset`, and `destroy`; wrapper contains `EventSource("/events")` but no duplicate render implementation.

Expected RED: core file/API is missing.

- [ ] **Step 5: Move state/render code mechanically first**

Refactor in two passes:

1. Move current state derivation and rendering into an instance closure without changing visible behavior.
2. Change selectors from `document.querySelector`/`getElementById` to root-scoped helpers.

Add `data-trace-viewer-root` to the existing `.shell` root. Do not reorder or rename any interior module.

The legacy wrapper must only:

```javascript
const root = document.querySelector("[data-trace-viewer-root]");
const viewer = window.MinAgentTraceViewer.create({ root });
const stream = new EventSource("/events");
stream.onmessage = (message) => viewer.applyEvent(JSON.parse(message.data));
```

plus connection/error cleanup. It must not contain a second `buildTaskPlan`, `buildRounds`, `renderTaskPlan`, or event store.

- [ ] **Step 6: Preserve initial and terminal behavior**

- Initial legacy page shows waiting state and empty Viewer.
- `loadRun()` uses supplied status/events and does not fabricate example events.
- `applyEvent()` preserves task/round auto-selection behavior.
- Completed/failed/interrupted selection remains the terminal completion view.
- `destroy()` closes internal listeners only; EventSource remains caller-owned.
- Core renders dynamic text with `textContent`/created text nodes, not unsanitized `innerHTML`.

- [ ] **Step 7: Run GREEN and full Viewer source regression**

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  tests.test_trace_viewer_source \
  tests.test_web_agent_source
```

Source GREEN is necessary but does not prove rendering parity.

- [ ] **Step 8: Re-run the legacy Viewer browser gate immediately after refactor**

Repeat Step 3 with a fresh run and the refactored `trace_viewer_core.js` + legacy wrapper. Use the same goal, workspace fixture content, permissions, viewport, and checkpoints. Compare behavior rather than generated timestamps or run IDs.

Required result:

```text
legacy Viewer refactor smoke: PASS
```

Also confirm the legacy page still connects only to `/events` and exposes no V1.0 launch, Key, history, or Web permission controls.

If any baseline checkpoint differs, stop inside Task 9, diagnose and fix the core extraction, rerun source tests, and rerun this browser gate. Do not begin Task 10 while the legacy Viewer gate is `FAIL` or `NOT RUN`.

## Task 10: Build the production Web shell, launch flow, and history replay

**Files:**

- Create: `web/web_agent.html`
- Create: `web/web_agent.css`
- Create: `web/web_agent.js`
- Modify: `tests/test_web_agent_source.py`

- [ ] **Step 1: Add failing page-structure tests from the accepted prototype**

Required outer elements:

```text
[data-route="new"]
[data-route="trace"]
[data-route="history"]
#pending-permission-button
#new-page
#workspace-value
#model-fake
#model-deepseek
#key-panel
#deepseek-key
#configure-key
#clear-key
#goal-input
#goal-count
#start-run
#service-status
#current-run-card
#run-meta-bar
#run-mode
#run-model
#run-workspace
#trace-page
#history-page
#history-list
#history-detail
```

`#workspace-value`, `#history-list`, and `#history-detail` are intentional production implementation hooks for unique lookup, dynamic rendering, and source tests. The accepted prototype used an unlabelled workspace `<code>` element and `.history-list` / `.history-detail` classes; it constrains their information architecture and visual hierarchy, not their exact DOM IDs. Keep the prototype classes alongside the new IDs where they own styling. Do not change layout merely to introduce these hooks.

The embedded `[data-trace-viewer-root]` must contain the exact frozen Viewer order and IDs. Assert launch, Key, history, and permission controls are outside it.

Assert production does not contain prototype state controls or hard-coded scene records.

- [ ] **Step 2: Add failing responsive/style assertions**

Source tests must require:

- desktop launch/history two-column layout;
- collapse to one column at narrow width;
- `min-width: 0` on grid/flex children that contain workspace/code/model content;
- responsive navigation and permission drawer width;
- Viewer stylesheet remains loaded before Web shell overrides;
- no horizontal fixed width larger than viewport;
- visible focus styles and disabled states.

These assertions prevent structural regression but do not prove actual layout.

- [ ] **Step 3: Add failing launch-state JavaScript assertions**

Required behavior/functions:

- bootstrap from `GET /api/state`;
- default hash `#/new`;
- valid hashes `#/new`, `#/trace`, `#/history`, `#/trace/<run_id>`;
- unknown hash falls back to launch without executing anything;
- workspace comes only from API response;
- Fake default and DeepSeek conditional Key panel;
- Key configured boolean controls UI, never a returned Key value;
- Key configure/clear controls are disabled during an active DeepSeek run and remain available during an active Fake run;
- goal trim/nonempty/1000-character count;
- start disabled during active run or missing DeepSeek Key;
- POST body contains only `goal` and `decision_model`;
- successful 201 navigates to `#/trace` only after response;
- failed request stays on launch and shows error;
- terminal current run permits a new start;
- history list comes from `/api/history`;
- replay loads `/api/history/<run_id>` and `viewer.loadRun()`;
- history replay sets mode/model/workspace metadata and never starts EventSource for the historical ID.

- [ ] **Step 4: Run RED**

```bash
env PYTHONDWRITEBYTECODE=1 python3 -m unittest tests.test_web_agent_source
```

- [ ] **Step 5: Implement production HTML from the prototype**

Use `docs/superpowers/v1.0/web-agent-prototype.html` as the visual reference, but remove:

- prototype state bar;
- hard-coded example scenes/history records;
- simulation buttons and `setDemo` logic;
- hard-coded absolute workspace;
- hard-coded completed/failed task state.

Keep:

- application header and three-page navigation;
- launch information hierarchy;
- Viewer-external metadata;
- embedded frozen Viewer;
- history master/detail layout;
- permission drawer markup added fully in Task 11;
- responsive visual hierarchy.

Load scripts in this order:

```html
<script src="./trace_viewer_core.js"></script>
<script src="./web_agent.js"></script>
```

- [ ] **Step 6: Implement hash routing and safe render helpers**

Use DOM creation and `textContent` for all API/event/user/model/file strings. Static controlled templates may remain HTML source. Do not insert API values through `innerHTML`.

Maintain one app state object containing only:

```javascript
{
  service,
  currentRun,
  activeRoute,
  selectedHistoryId,
  historyRows,
  pendingPermission,
  currentEventSource,
  viewingHistoricalRunId,
  lastFocusedElement
}
```

Do not store the DeepSeek Key in app state. Read it from the password input only while constructing the PUT body, then clear the input in `finally` after a completed request.

Do not use `localStorage`, `sessionStorage`, IndexedDB, Cookie, URL query, or hash for the Key.

- [ ] **Step 7: Implement launch and history API flow**

Use one `apiFetch()` helper that:

- sends same-origin requests;
- sets JSON content type for mutation bodies;
- parses the envelope;
- throws a sanitized UI error using only server error code/message;
- never logs body or response data;
- handles non-JSON server failure without exposing raw HTML.

History replay must call:

```javascript
viewer.loadRun({
  runId: record.run_id,
  status: record.status,
  events: record.events,
});
```

Simple historical records hide task plan because the shared Viewer derives no `plan_created`; composite records show the saved plan/artifacts.

- [ ] **Step 8: Run GREEN source tests**

```bash
env PYTHONDWRITEBYTECODE=1 python3 -m unittest \
  tests.test_web_agent_source \
  tests.test_trace_viewer_source
```

Do not report browser PASS yet.

## Task 11: Add current-run SSE state, permission drawer, and refresh recovery

**Files:**

- Modify: `web/web_agent.html`
- Modify: `web/web_agent.css`
- Modify: `web/web_agent.js`
- Modify: `tests/test_web_agent_source.py`
- Modify: `tests/test_web_server.py` only if an actual client recovery case exposes a missing API contract

- [ ] **Step 1: Add failing permission DOM assertions**

Require the production page to contain, outside `[data-trace-viewer-root]`:

```text
#permission-backdrop
#permission-drawer
#permission-title
#permission-run
#permission-tool
#permission-reason
#permission-workspace
#permission-target
#permission-preview
#permission-risk
#close-permission
#reject-permission
#approve-permission
```

These field-level permission IDs are intentional implementation hooks for accessible labelling, safe `textContent` updates, unique source-test targeting, and focus management. The prototype used `.permission-drawer`, `.permission-detail`, and `data-close-drawer` without IDs for every field; it constrains the drawer's information order, hierarchy, and visual behavior, not the exact field IDs. Preserve the prototype classes and visible structure while adding these IDs. Do not treat the missing prototype IDs as permission to redesign the drawer.

Initial drawer requirements:

- `aria-hidden="true"`;
- `inert` present;
- backdrop cannot receive pointer events;
- no hidden approve/reject controls remain tabbable.

- [ ] **Step 2: Add failing live-state source assertions**

Require:

- exactly one current-run `EventSource` owner in `web_agent.js`;
- exact run ID encoded in the SSE URL;
- snapshot loaded before stream connection;
- event run ID checked before state/viewer update;
- dedupe delegated to Viewer core;
- `onopen` clears reconnecting status;
- `onerror` displays reconnecting without marking run failed;
- native EventSource reconnection is not combined with a second timer-created stream;
- terminal event closes the source;
- route switch to history does not close the current-run source;
- current events update global state while historical Viewer remains unchanged;
- returning to `#/trace` reloads current snapshot;
- page bootstrap fetches pending permission even before a new SSE event;
- a bounded pending-snapshot handoff retry handles the moment after `permission_requested` is emitted but before `PermissionBroker.request()` has published its snapshot;
- no page action directly declares tool execution or run completion.

- [ ] **Step 3: Add failing permission behavior assertions**

Require functions/behavior for:

- `refreshPendingPermission()`;
- `openPermissionDrawer()`;
- `closePermissionDrawer()`;
- `resolvePermission(approved)`;
- pending global button reopening the same request;
- closing/Escape/route change preserving pending state;
- approve/reject buttons disabled during request;
- success closes drawer only after API confirmation;
- 409 stale/already-resolved response refreshes server truth;
- focus moves into the open drawer and returns to the prior connected element on close;
- history replay cannot supply a permission ID or decision;
- drawer always labels the active run, even while Viewer displays history.

- [ ] **Step 4: Run RED**

```bash
env PYTHONDWRITEBYTECODE=1 python3 -m unittest tests.test_web_agent_source
```

- [ ] **Step 5: Implement one global current-run stream**

Bootstrap order:

```text
create Viewer core
-> GET /api/state
-> render service/launch/current snapshot
-> GET /api/permissions/current
-> connect current active run SSE
-> apply hash route
-> load history only if needed
```

When POST run succeeds:

```text
store returned current snapshot
-> viewer.loadRun(snapshot)
-> close old EventSource if any
-> open exact new-run EventSource
-> navigate #/trace
```

When a current event arrives:

```text
validate run_id
-> update current snapshot event/status
-> if current trace mode, viewer.applyEvent(event)
-> if permission_requested, refresh/open current permission
-> if permission_resolved, refresh/close pending UI
-> if terminal, close stream and refresh service/history state
```

Do not interpret a transport `onerror` as Agent failure. Only TraceEvent or snapshot terminal status may mark the run terminal.

Because existing `AgentLoop` emits `permission_requested` immediately before invoking the permission callback, an SSE client can theoretically receive that event before the Broker snapshot is visible. When that exact condition occurs, `refreshPendingPermission()` may retry at 50, 100, 200, 400, and 800 ms, stopping as soon as a snapshot appears, the permission is resolved, the run becomes terminal, or the run ID changes. Maintain at most one retry chain. Do not turn this into permanent polling.

- [ ] **Step 6: Implement accessible permission behavior**

- Remove `inert`, set `aria-hidden=false`, reveal backdrop, store prior focus, then focus the primary safe action only after drawer opens.
- Keep approve visually primary and reject explicit; do not default an Enter key handler that can approve from arbitrary focus.
- On close, set `aria-hidden=true`, restore `inert`, hide backdrop, and restore focus if the element is still connected.
- Escape closes only the drawer, not the permission request.
- While the decision request is in flight, disable both buttons.
- Render all fields with `textContent`.
- Hide sections with no applicable data rather than displaying fabricated placeholders.
- Never include Key configuration state or value in permission content.

- [ ] **Step 7: Implement refresh recovery**

Refreshing in each state must recover from server truth:

| Server state | Required page recovery |
| --- | --- |
| ready, no run | launch ready; trace waiting |
| busy | current card shown; start disabled; stream connected |
| approval_required | start disabled; pending button visible; drawer can reopen |
| terminal current snapshot | service ready; final Viewer available; new run allowed |
| historical hash | selected saved record rendered; current global state still maintained |

Do not store current run or pending permission in browser persistence to simulate recovery.

- [ ] **Step 8: Run GREEN source tests**

```bash
env PYTHONDWRITEBYTECODE=1 python3 -m unittest \
  tests.test_web_agent_source \
  tests.test_trace_viewer_source
```

Browser behavior remains unproven until Task 12.

## Task 12: Add complete Web Agent scenarios and perform real browser acceptance

**Files:**

- Create: `tests/test_web_scenarios.py`
- Modify: `tests/test_web_server.py`
- Modify: `tests/test_run_manager.py`
- Modify: `tests/test_cli_scenarios.py` only for explicit legacy regression
- Record results later in: `docs/runbook.md` and `CHANGELOG.md`

- [ ] **Step 1: Write full HTTP-to-AgentLoop scenario tests**

Use:

- `tempfile.TemporaryDirectory()` for test-owned workspace and runs directories;
- actual `WebAgentServer` on port 0;
- actual JSON HTTP requests;
- actual `RunManager`, `AgentLoop`, `TraceRecorder`, `ToolRegistry`, and workspace tools;
- `step_delay_seconds=0`;
- deterministic DecisionModel test doubles only where real DeepSeek HTTP would otherwise be required.

Do not replace AgentLoop with a fake in end-to-end scenarios.

- [ ] **Step 2: Cover the Fake simple scenario**

POST:

```json
{"goal": "请读取 notes.md 并总结", "decision_model": "fake"}
```

Assert:

- 201 with one run ID;
- second start during active run is 409;
- SSE/run record contains `run_started -> context_built -> llm_decision -> tool_started(read_file) -> tool_finished -> observation_added -> final_answer -> run_completed` in semantic order;
- no `plan_created`, permission request, or task artifact;
- terminal snapshot and history record match;
- service is ready for the next run.

- [ ] **Step 3: Cover the composite approval scenario**

Run the canonical four-task Fake goal so no external Key/network is required.

Drive both real Web permissions through HTTP:

1. Wait until `GET /api/permissions/current` returns `run_command`.
2. Approve its exact ID once.
3. Wait for `write_file` permission.
4. Approve its exact ID once.

Assert:

- permission_requested precedes permission_resolved;
- permission_resolved(true) precedes corresponding tool_started;
- actual `summary.md` is created inside the temporary workspace;
- 4 tasks complete with available artifacts;
- final answer and saved record show completion;
- duplicate approval is 409 and each tool starts exactly once;
- record contains no configured Key field/value.

- [ ] **Step 4: Cover both rejection boundaries**

Separate scenarios:

- reject `run_command`: no `tool_started(run_command)`, task 3 failed, task 4 skipped, no summary file;
- approve `run_command`, reject `write_file`: no `tool_started(write_file)`, summary file absent, failure saved.

In both cases, closing the page is not simulated as a decision; only the explicit API boolean resolves the request.

- [ ] **Step 5: Cover Key/model isolation**

Use a sentinel Key only in process memory and a deterministic DeepSeek decision-model factory.

Assert:

- state and Key PUT response contain configured boolean only;
- a DeepSeek run uses the injected Key once;
- a controlled DeepSeek model failure produces a failed run record while the Web service stays available;
- a Fake run before/after it never calls `require()`;
- clear succeeds after terminal DeepSeek run;
- clear fails during active DeepSeek run;
- API responses, captured logs, Trace events, saved records, history summaries, and final answers do not contain the sentinel;
- Web service never reads a conflicting `DEEPSEEK_API_KEY` environment value;
- legacy CLI test still reads its environment Key path.

- [ ] **Step 6: Cover sequential and historical isolation**

Run simple -> failed composite -> successful composite in the same service.

Assert:

- three unique IDs;
- one active run maximum;
- each saved record contains only its own events;
- history order is newest first;
- simple history has no plan;
- composite histories have their exact task/artifact states;
- requesting current SSE with a historical ID fails;
- loading history while current run executes does not mutate either record;
- a current permission decision changes only current run.

- [ ] **Step 7: Prove existing tool safety through the Web run path**

Use controlled DecisionModels that propose malicious or invalid local actions through the real AgentLoop:

- `read_file` with `../`;
- workspace-outside absolute path;
- symlink whose target is outside workspace;
- `run_command` with unknown `command_id`.

Assert:

- file actions return structured tool errors and never read outside content;
- unknown command fails validation before `permission_requested`;
- no forged Web request can call a tool endpoint directly because none exists;
- no invalid action produces `tool_started`;
- service stays alive and saves the failed run;
- existing workspace and command safety tests remain green.

- [ ] **Step 8: Cover restart/refresh server truth**

At backend integration level:

- call state/current/pending endpoints multiple times during one pending request;
- verify the same IDs and state return without resolving it;
- disconnect one SSE client and connect another;
- verify history + subsequent events reconstruct the same ordered sequence;
- ensure no duplicate tool execution;
- stop service during pending permission and verify interrupted record, no user-rejected event, and waiting HTTP/SSE threads close.

- [ ] **Step 9: Run RED then GREEN scenario tests**

```bash
env PYTHONDWRITEBYTECODE=1 python3 -m unittest tests.test_web_scenarios
```

Expected RED before scenario wiring is complete. After implementation, rerun:

```bash
env PYTHONDWRITEBYTECODE=1 python3 -m unittest \
  tests.test_web_scenarios \
  tests.test_web_server \
  tests.test_run_manager \
  tests.test_permission_broker \
  tests.test_workspace_tools \
  tests.test_command_registry \
  tests.test_command_tool
```

- [ ] **Step 10: Prepare a non-repository browser acceptance workspace**

Do not use a workspace containing user files and do not create `summary.md` in the checked-in example workspace.

Create a dedicated acceptance directory under `/private/tmp`, copy only the example fixture files, and use a runs subdirectory there. Record the exact path. Do not delete it without separate user authorization.

Example preparation shape:

```text
/private/tmp/min-agent-v1.0-acceptance-<id>/
├── workspace/
│   ├── notes.md
│   ├── project.md or other copied example fixtures
│   └── minagent.md if required by the scenario
└── runs/
```

Start:

```bash
PYTHONPATH=src python3 -m min_agent.web_app \
  --workspace /private/tmp/min-agent-v1.0-acceptance-<id>/workspace \
  --runs-dir /private/tmp/min-agent-v1.0-acceptance-<id>/runs \
  --port 0 \
  --no-browser \
  --step-delay 0
```

- [ ] **Step 11: Perform real desktop browser acceptance**

Using the actual printed URL, verify with real interaction:

1. Page is nonblank and defaults to launch.
2. Workspace is the service value and cannot be edited.
3. Fake is default; DeepSeek reveals Key controls.
4. Configure a non-real sentinel Key; input clears; refresh shows only configured state; clear removes it.
5. Run Fake simple goal; automatic trace navigation works; no task plan appears.
6. Return to launch and start canonical composite Fake goal in the same service.
7. Current-run card and start-disabled state are correct.
8. On `run_command` permission, drawer opens with actual validated command/risk.
9. Close drawer; run remains waiting; pending button remains; reopen it.
10. Refresh while pending; same request recovers and no decision occurs.
11. Approve once; Agent continues and tool starts once.
12. Approve `write_file`; final file appears only in acceptance workspace; 4/4/artifacts/final answer agree.
13. Run a rejection scenario and verify failed/skipped/artifact states agree.
14. Open history and replay simple, successful composite, and failed composite records.
15. Simple replay hides plan; composite replay shows correct plan/artifacts.
16. While viewing history during a current pending run, global approval entry still refers to current run and the historical Viewer does not change.
17. Refresh current, history list, and history replay routes; server truth restores each view.
18. Force one SSE disconnect/reconnect; event steps remain unique and no other run ID appears.
19. No JavaScript errors or unhandled promise rejections appear in Console.
20. Network panel shows Key only in the one PUT request body and never in URL/response/subsequent request.
21. Browser storage inspection shows no Key in local/session storage, IndexedDB, Cookies, or cache.

Do not perform a real DeepSeek network call unless the user separately supplies a Key for that acceptance. Absence of a real-Key smoke does not invalidate deterministic backend model wiring tests, but it must be recorded honestly as `real DeepSeek browser smoke: NOT RUN`.

- [ ] **Step 12: Perform 390px narrow-screen acceptance**

Set viewport to 390x844 and verify:

- no document-level horizontal overflow;
- nav buttons and pending entry remain usable;
- workspace text truncates/wraps without widening page;
- model cards, Key row, launch layout, metadata grid, task cards, artifact flow, history, and detail grids collapse correctly;
- permission drawer fits viewport and both decisions are reachable;
- Viewer rounds/detail remain readable;
- Console remains clean.

- [ ] **Step 13: Record browser evidence honestly**

Only write `browser manual smoke: PASS` if the actual production service and page completed the checks above. Otherwise write `NOT RUN` or `FAIL` with the exact blocked/failed step.

Source checks, prototype interaction, or HTTP tests cannot substitute for this result.

## Task 13: Finish user documentation and perform final completion audit

**Files:**

- Modify: `README.md`
- Modify: `docs/runbook.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_project_testing_rules.py` if user-documentation markers are guarded
- Verify: all V1.0 runtime, Web, test, prototype, and product files

- [ ] **Step 1: Update README for the actual implemented entry**

Document:

- exact Web service command and printed URL;
- launch -> permission -> process -> history workflow;
- Fake default and per-run model choice;
- process-memory Key lifecycle and clear behavior;
- one active run/no queue;
- fixed workspace;
- V0.9 Viewer reuse;
- existing one-shot CLI compatibility;
- explicit V1.0 non-goals.

Do not claim real DeepSeek browser success unless it was actually run.

- [ ] **Step 2: Update runbook with operational and diagnostic procedures**

Include:

- startup, port 0, no-browser, and shutdown;
- how to distinguish service startup errors, API validation, Agent failure, permission rejection, SSE reconnect, and corrupt history;
- Fake simple and composite approve/reject scenarios;
- Key configure/clear rules without showing a real Key;
- run-record location and new decision-model metadata;
- full unit/scenario commands;
- browser acceptance result and exact acceptance workspace path;
- generated artifacts and cleanup status.

- [ ] **Step 3: Update CHANGELOG as a product record**

The V1.0 entry must explain:

- what problem the local Web Agent closes;
- what users can now do;
- preserved Agent/tool/Viewer boundaries;
- what V1.0 does not do;
- automated test result;
- browser manual smoke result;
- real DeepSeek browser smoke result separately;
- generated artifact and cleanup status.

Do not write a commit-file list as the release note.

- [ ] **Step 4: Run all targeted V1.0 tests**

```bash
env PYTHONDWRITEBYTECODE=1 python3 -m unittest \
  tests.test_runtime_factory \
  tests.test_session_key_store \
  tests.test_permission_broker \
  tests.test_run_history \
  tests.test_run_manager \
  tests.test_web_server \
  tests.test_web_app \
  tests.test_web_agent_source \
  tests.test_web_scenarios
```

- [ ] **Step 5: Run complete regression**

```bash
env PYTHONDWRITEBYTECODE=1 python3 -m unittest discover -s tests
```

Required result: exit 0 and final `OK`. The count must be greater than the 377-test V0.9 baseline. Do not set a target count by padding trivial tests.

- [ ] **Step 6: Run text, structure, and diff checks**

```bash
git diff --check
git status --short --branch
git diff --stat
git diff -- AGENTS.md README.md CHANGELOG.md docs/runbook.md src web tests
```

Because V1.0 files may be untracked, separately inspect:

```text
docs/superpowers/v1.0/product-design.md
docs/superpowers/v1.0/web-agent-prototype.html
docs/superpowers/v1.0/implementation-plan.md
```

Check Markdown trailing whitespace and balanced code fences with a read-only standard-library script. Do not rely on `git diff --check` for untracked files.

- [ ] **Step 7: Run secret and forbidden-storage audit**

Search the exact sentinel values used in automated/browser acceptance across:

```text
repository files
acceptance runs directory
captured service output
run records
browser localStorage/sessionStorage/IndexedDB/Cookies/cache
```

The exact sentinels must be absent after the Key request body. Legitimate documentation references to `DEEPSEEK_API_KEY`, `.env`, or `localStorage` are not leaks by themselves; inspect context rather than deleting required security documentation.

Also verify:

```bash
rg -n "localStorage|sessionStorage|indexedDB|document\.cookie" web src/min_agent
```

Expected: no Key persistence implementation. If a term appears only in a guard/test/comment, verify it cannot store the Key.

- [ ] **Step 8: Re-run browser smoke after the final code change**

If any runtime, HTML, CSS, or JavaScript changed after Task 12, rerun all affected browser checks. A browser PASS obtained before the final change is stale evidence.

- [ ] **Step 9: Report but do not clean, commit, or publish**

Report:

- files changed/added;
- full test count and elapsed time;
- browser PASS/FAIL/NOT RUN;
- real DeepSeek smoke PASS/FAIL/NOT RUN;
- acceptance directory and generated files;
- unresolved limitations;
- current Git status.

Do not delete the acceptance directory or generated artifacts, stage, commit, tag, merge, or push without separate user confirmation.

## 6. Test and acceptance matrix

| Requirement | Unit/source proof | Scenario/runtime proof | Browser proof |
| --- | --- | --- | --- |
| Long-running one-start service | `test_web_app.py` | sequential runs in one server | second task without restart |
| Fixed workspace | server/run-manager tests | forged workspace rejected | workspace visibly locked |
| Fake default/no Key read | factory/key/manager tests | Fake with raising Key Store | default selection and successful Fake run |
| Web DeepSeek Key memory only | key/server/source tests | sentinel leak audit | configure, refresh boolean, clear, storage check |
| One active run/no queue | manager/server tests | concurrent POST conflict | start disabled/current card |
| AgentLoop/ToolRegistry reuse | factory and regression tests | real end-to-end AgentLoop events | real Trace path |
| Web permission approval | broker/server tests | approve both tools via API | drawer approve and continuation |
| Web permission rejection | broker/permission regression | no corresponding tool_started | reject and failed Viewer |
| Drawer close is not rejection | source/broker tests | repeated pending endpoint | close/reopen/refresh same request |
| Decision exactly once | broker/server tests | duplicate approval 409, one tool start | buttons disable/resolve once |
| SSE recovery and isolation | server/core tests | disconnect/reconnect and run IDs | refresh/reconnect, no mixed history |
| History from run records | history tests | sequential saved records | simple/composite/failed replay |
| Historical permissions read-only | API/source tests | history load cannot resolve | current permission while viewing history |
| V0.9 Viewer frozen | Viewer source tests | same events/core in both modes | module order and task/artifact interactions |
| Legacy CLI compatibility | CLI/unit regressions | existing CLI scenarios | legacy Viewer smoke if changed |
| Loopback/same-origin security | server Host/Origin tests | actual local HTTP rejects forged calls | Network panel same origin |
| XSS-safe dynamic rendering | source tests | hostile goal/event fixture | hostile text displays as text |
| Responsive layout | source structure guards | n/a | 390x844 no overflow |
| Failure convergence | manager/server tests | model/tool/key/history failures | visible actionable error, service survives |
| No secret leakage | source/key tests | sentinel audit of responses/logs/records | request-only Key and empty storage |

## 7. Explicit non-goals and rejection conditions

Reject the implementation if any of the following occurs:

- Web mode reads `DEEPSEEK_API_KEY`, writes `.env`, or persists a Key anywhere.
- Fake calls `SessionKeyStore.require()` or fails because no Key exists.
- API returns a Key fragment, mask, hash, length-derived fingerprint, or raw exception containing it.
- Browser stores the Key after the configuration request.
- Page can submit or change workspace, runs directory, model name, Base URL, command text, or tool registry.
- Service binds to `0.0.0.0`, accepts arbitrary Host/Origin, or enables CORS.
- A second run starts while the first is running or waiting for permission.
- A request is queued instead of rejected.
- AgentLoop runs in an HTTP request thread.
- Permission waiting blocks state, history, static, or decision HTTP requests.
- Closing a drawer/page or losing SSE resolves a permission.
- A permission ID can be approved twice or execute a tool twice.
- Rejected permission produces corresponding `tool_started`.
- Service-shutdown cancellation is recorded as user rejection.
- Historical replay connects to current SSE as if it were that historical run.
- Current events mutate the historical Viewer.
- History data comes from hard-coded frontend examples or mutable browser state.
- History adds delete, rename, export, rerun, resume, or record-edit controls.
- Corrupt history record makes the whole list unavailable.
- Viewer rendering is copied into a separate implementation in `web_agent.js`.
- V0.9 Viewer module order, key IDs, artifacts, rounds, or read-only behavior changes.
- Launch/Key/permission/history controls are inserted inside the Viewer root.
- Prototype state controls or fake scene data ship in production.
- Dynamic API/model/file/user text is assigned through unsafe `innerHTML`.
- Existing CLI loses flags, changes Key source, changes terminal permission semantics, or opens the launch page instead of its trace view.
- Tests pass because an assertion was weakened, a current test removed, an exception swallowed, or a race hidden with sleeps.
- Browser acceptance is marked PASS from source tests, the static prototype, or HTTP calls only.
- Real DeepSeek smoke is marked PASS without an actual real-Key model call.
- Implementation adds login, remote access, multi-user, multi-workspace, concurrent run, queue, retry, resume, cancel, plan editing, arbitrary command, database, framework, SDK, long-term memory, multi-Agent, MCP, Hook, or plugin system.
- The page adds a service-stop control or any operation that replaces terminal `Ctrl+C` shutdown.

## 8. Completion definition

V1.0 is complete only when every item below has direct current-state evidence:

1. One command starts a persistent `127.0.0.1` Web service without a goal or Key.
2. The default page is launch and the server-fixed workspace cannot be changed from Web input or forged JSON.
3. Fake and DeepSeek are the only per-run model choices, and the choice freezes at run creation.
4. Fake works with no Key and never accesses Key Store.
5. Web DeepSeek uses only a process-memory Key and never environment fallback.
6. Configured Key cannot be read back and is absent from files, logs, Trace, records, responses, URLs, and browser storage.
7. Service owns at most one active run and rejects another rather than queueing.
8. Agent work occurs in a background thread while HTTP remains responsive.
9. Current state and events come from real RunManager/TraceRecorder state.
10. Run creation automatically enters the process page only after 201 success.
11. Snapshot plus run-scoped SSE reconstructs the same current run after refresh/reconnect.
12. Current `write_file` and `run_command` permissions can be approved/rejected in Web.
13. Closing/reloading/changing route does not resolve pending permission.
14. Each permission resolves at most once and denial never starts its tool.
15. Service shutdown cancels pending waits and saves interruption without claiming user rejection.
16. Terminal run returns the service to ready and a second sequential run succeeds without restart.
17. Every new terminal Web run has a saved record with decision-model metadata.
18. History lists validated saved records newest first and isolates malformed records.
19. Simple, successful composite, and failed composite histories replay correctly through the shared Viewer.
20. Historical Viewer is isolated from current SSE and current permissions.
21. One shared Viewer core powers legacy CLI and Web Agent rendering.
22. V0.9 Viewer interior order, IDs, task artifacts, rounds, and read-only behavior remain unchanged.
23. Existing one-shot CLI Fake/DeepSeek, terminal permission, flags, exit codes, and Trace Server remain green.
24. Host/Origin/body/static/path tests prove the local HTTP boundary.
25. Full automated suite exceeds the 377-test baseline and exits with `OK`.
26. Actual production browser acceptance passes desktop and 390px checks with a clean Console.
27. Real DeepSeek browser status is reported separately and honestly.
28. README, runbook, CHANGELOG, AGENTS, PRD, prototype, and this plan agree with implemented behavior.
29. Generated acceptance artifacts and cleanup status are reported without unauthorized deletion.
30. No commit, tag, merge, push, deployment, dependency installation, secret/config change, or cleanup occurs without separate authorization.
