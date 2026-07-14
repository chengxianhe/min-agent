const state = {
  status: "waiting",
  events: [],
  selectedRoundId: null,
  selectedTaskId: null,
  userSelectedTask: false,
};

function connectTraceStream() {
  if (!("EventSource" in window)) {
    setStatus("unsupported");
    return;
  }

  const stream = new EventSource("/events");
  stream.onmessage = (message) => {
    const event = JSON.parse(message.data);
    applyEvent(event);
  };
  stream.onerror = () => {
    if (!isTerminalStatus(state.status)) {
      setStatus("reconnecting");
    }
  };
}

function applyEvent(event) {
  const existingIndex = state.events.findIndex((item) => item.step === event.step);
  if (existingIndex >= 0) {
    state.events[existingIndex] = event;
  } else {
    state.events.push(event);
  }

  // V0.8: auto-select first task on plan creation
  if (event.phase === "plan_created") {
    const plan = buildTaskPlan(state.events);
    if (plan && plan.definitions.length > 0) {
      state.selectedTaskId = plan.definitions[0].task_id;
      state.userSelectedTask = false;
    }
  }

  // V0.8: when a new lifecycle event changes active task, override user selection
  if (["task_started", "task_failed"].includes(event.phase)) {
    state.userSelectedTask = false;
  }

  const rounds = buildRounds(state.events);
  const latestRound = rounds[rounds.length - 1];
  if (["run_completed", "run_failed", "run_interrupted"].includes(event.phase)) {
    const plan = buildTaskPlan(state.events);
    if (plan && plan.definitions.length > 0) {
      state.selectedTaskId = plan.definitions[plan.definitions.length - 1].task_id;
      state.userSelectedTask = false;
    }
    state.selectedRoundId = "task-completion";
  } else {
    state.selectedRoundId = latestRound?.id || (event.phase === "run_started" ? "task-entry" : null);
  }
  state.status = event.status || state.status;
  render();
}

function setStatus(status) {
  state.status = status;
  renderStatus();
}

function isTerminalStatus(status) {
  return ["completed", "failed", "interrupted"].includes(status);
}

function buildRunSummary(events) {
  const rounds = buildRounds(events);
  return {
    rounds: rounds.filter((round) => round.events.some((event) => event.phase === "llm_decision")).length,
    modelCalls: events.filter((event) => event.phase === "llm_decision").length,
    toolCalls: events.filter((event) => event.phase === "tool_started").length,
    contextBuilds: events.filter((event) => event.phase === "context_built").length,
    permissions: events.filter((event) => event.phase === "permission_requested").length,
  };
}

// ---- V0.8: task plan state derivation ----

function buildTaskPlan(events) {
  const planEvent = events.find((e) => e.phase === "plan_created");
  if (!planEvent || !planEvent.output || !Array.isArray(planEvent.output.tasks)) {
    return null;
  }

  const definitions = planEvent.output.tasks.map((t) => ({
    task_id: t.task_id,
    title: t.title,
    completion_criteria: t.completion_criteria,
  }));

  if (definitions.length < 2 || definitions.length > 5) {
    return null;
  }

  // Apply lifecycle events by stable ID
  const statuses = {};
  const failureReasons = {};
  for (const d of definitions) {
    statuses[d.task_id] = "pending";
    failureReasons[d.task_id] = "";
  }

  for (const event of events) {
    const tid = event.task_id || event.output?.task_id;
    if (!tid) continue;

    if (event.phase === "task_started" && statuses[tid] === "pending") {
      statuses[tid] = "running";
    } else if (event.phase === "task_completed") {
      statuses[tid] = "completed";
    } else if (event.phase === "task_failed") {
      statuses[tid] = "failed";
      failureReasons[tid] = event.output?.failure_reason || "";
    } else if (event.phase === "task_skipped") {
      statuses[tid] = "skipped";
      failureReasons[tid] = event.output?.failure_reason || "";
    }
  }

  // Find current running/failed task
  let activeTaskId = null;
  for (const d of definitions) {
    if (statuses[d.task_id] === "running" || statuses[d.task_id] === "failed") {
      activeTaskId = d.task_id;
      break;
    }
  }

  return {
    definitions,
    statuses,
    failureReasons,
    activeTaskId,
    completedCount: Object.values(statuses).filter((s) => s === "completed").length,
    totalCount: definitions.length,
    artifacts: buildTaskArtifacts(events),
  };
}

function buildTaskArtifacts(events) {
  const artifacts = {};
  for (const event of events) {
    if (!["task_artifact_created", "task_artifact_missing"].includes(event.phase)) continue;
    const artifact = event.output?.artifact;
    const taskId = event.task_id || artifact?.task_id;
    if (!taskId || !artifact || typeof artifact !== "object") continue;
    artifacts[taskId] = {
      artifact,
      evidenceObservations: Array.isArray(event.output?.evidence_observations) ? event.output.evidence_observations : [],
      inheritedTaskIds: Array.isArray(event.output?.inherited_task_ids) ? event.output.inherited_task_ids : [],
      forwardedTaskIds: Array.isArray(event.output?.forwarded_task_ids) ? event.output.forwarded_task_ids : [],
    };
  }
  return artifacts;
}

function artifactForTask(plan, taskId) {
  return plan?.artifacts?.[taskId] || null;
}

function renderTaskPlan() {
  const plan = buildTaskPlan(state.events);
  const panel = document.querySelector("#task-plan-panel");

  if (!plan) {
    panel.hidden = true;
    state.selectedTaskId = null;
    state.userSelectedTask = false;
    const label = document.querySelector("#selected-task-label");
    label.hidden = true;
    label.textContent = "";
    return;
  }

  panel.hidden = false;

  // Progress
  const progressEl = document.querySelector("#task-progress-text");
  const allDone = plan.completedCount === plan.totalCount && !plan.activeTaskId;
  const hasFailure = Object.values(plan.statuses).some((s) => s === "failed");
  progressEl.textContent = allDone && !hasFailure
    ? `${plan.completedCount} / ${plan.totalCount} 完成`
    : `${plan.completedCount} / ${plan.totalCount} 任务`;

  // Task list
  const list = document.querySelector("#task-list");
  list.replaceChildren();

  for (const def of plan.definitions) {
    const tid = def.task_id;
    const status = plan.statuses[tid] || "pending";
    const reason = plan.failureReasons[tid] || "";

    const card = document.createElement("li");
    card.className = `task-card task-${status}`;
    if (tid === state.selectedTaskId) {
      card.classList.add("task-selected");
    }

    const top = document.createElement("div");
    top.className = "task-top";

    const index = document.createElement("span");
    index.className = "task-index";
    index.textContent = tid.replace("task-", "");

    const title = document.createElement("span");
    title.className = "task-title";
    title.textContent = def.title;

    const statusBadge = document.createElement("span");
    statusBadge.className = "task-status";
    const statusLabels = { pending: "待执行", running: "执行中", completed: "已完成", failed: "失败", skipped: "已跳过" };
    statusBadge.textContent = statusLabels[status] || status;

    top.append(index, title, statusBadge);

    if (reason) {
      const error = document.createElement("p");
      error.className = "task-error";
      error.textContent = reason;
      card.append(top, error);
    } else {
      card.append(top);
    }

    card.addEventListener("click", () => {
      selectTask(tid);
      render();
    });

    list.append(card);
  }

  // Auto-select active task
  if (!state.userSelectedTask && plan.activeTaskId) {
    state.selectedTaskId = plan.activeTaskId;
  } else if (!state.userSelectedTask && !plan.activeTaskId && plan.definitions.length > 0) {
    if (!state.selectedTaskId || !plan.definitions.find((d) => d.task_id === state.selectedTaskId)) {
      state.selectedTaskId = plan.definitions[0].task_id;
    }
  }

  // Update selected-task label
  const label = document.querySelector("#selected-task-label");
  const selectedDef = plan.definitions.find((d) => d.task_id === state.selectedTaskId);
  if (selectedDef) {
    label.hidden = false;
    const status = plan.statuses[state.selectedTaskId] || "pending";
    const statusLabels = { pending: "待执行", running: "执行中", completed: "已完成", failed: "失败", skipped: "已跳过" };
    label.textContent = `当前任务：${selectedDef.title}（${statusLabels[status] || status}）`;
  } else {
    label.hidden = true;
    label.textContent = "";
  }
  renderSelectedTaskArtifact(plan);
}

function formatArtifactEvidence(item) {
  return `Observation ${item.index}: ${item.tool_name}`;
}

function renderArtifactChips(plan, taskIds, emptyText) {
  const list = document.createElement("div");
  list.className = "artifact-chip-list";
  if (!taskIds.length) {
    const empty = document.createElement("span");
    empty.className = "artifact-none";
    empty.textContent = emptyText;
    list.append(empty);
    return list;
  }
  for (const taskId of taskIds) {
    const definition = plan.definitions.find((item) => item.task_id === taskId);
    const chip = document.createElement("span");
    chip.className = "artifact-chip";
    chip.textContent = definition ? `${definition.task_id} · ${definition.title}` : taskId;
    list.append(chip);
  }
  return list;
}

function renderSelectedTaskArtifact(plan) {
  const title = document.querySelector("#task-artifact-title");
  const status = document.querySelector("#task-artifact-status");
  const body = document.querySelector("#task-artifact-body");
  body.replaceChildren();
  const def = plan.definitions.find((item) => item.task_id === state.selectedTaskId);
  if (!def) {
    title.textContent = "所选任务产物";
    status.textContent = "waiting";
    return;
  }
  const record = artifactForTask(plan, def.task_id);
  const artifact = record?.artifact;
  title.textContent = `${def.title}的任务产物`;
  status.textContent = artifact?.status || "waiting";
  status.className = `task-artifact-status status-${artifact?.status || "waiting"}`;

  if (!artifact) {
    const empty = document.createElement("div");
    empty.className = "artifact-empty";
    const heading = document.createElement("strong");
    heading.textContent = "本任务尚未产生产物";
    const detail = document.createElement("p");
    detail.textContent = "任务完成后，这里会展示可继承的正式产物。";
    empty.append(heading, detail);
    body.append(empty);
    return;
  }
  if (artifact.status === "missing") {
    const empty = document.createElement("div");
    empty.className = "artifact-empty artifact-missing";
    const heading = document.createElement("strong");
    heading.textContent = "本任务没有产物";
    const reason = document.createElement("p");
    reason.textContent = artifact.missing_reason || "没有可校验的成功 Observation。";
    const inherited = document.createElement("p");
    inherited.textContent = record.inheritedTaskIds.length
      ? `进入失败任务前已注入：${record.inheritedTaskIds.join("、")}`
      : "该任务未继承前序产物。";
    empty.append(heading, reason, inherited);
    body.append(empty);
  } else {
    const grid = document.createElement("div");
    grid.className = "artifact-grid";

    const contentSection = document.createElement("section");
    contentSection.className = "artifact-section artifact-content";
    const contentHeading = document.createElement("h4");
    contentHeading.textContent = "主产物内容";
    const content = document.createElement("pre");
    content.id = "artifact-content";
    content.textContent = artifact.content;
    contentSection.append(contentHeading, content);

    const evidenceSection = document.createElement("section");
    evidenceSection.className = "artifact-section artifact-evidence";
    const evidenceHeading = document.createElement("h4");
    evidenceHeading.textContent = "当前任务 Observation 来源";
    const evidenceList = document.createElement("ul");
    evidenceList.id = "artifact-evidence";
    evidenceList.className = "evidence-list";
    if (!record.evidenceObservations.length) {
      const item = document.createElement("li");
      item.textContent = "没有可校验的当前任务 Observation。";
      evidenceList.append(item);
    } else {
      for (const evidence of record.evidenceObservations) {
        const item = document.createElement("li");
        item.textContent = formatArtifactEvidence(evidence);
        evidenceList.append(item);
      }
    }
    evidenceSection.append(evidenceHeading, evidenceList);
    grid.append(contentSection, evidenceSection);
    body.append(grid);
  }
  const flow = document.createElement("div");
  flow.className = "artifact-flow";
  const appendFlowBlock = (label, taskIds, emptyText) => {
    const block = document.createElement("section");
    block.className = "artifact-flow-block";
    const heading = document.createElement("strong");
    heading.textContent = label;
    block.append(heading, renderArtifactChips(plan, taskIds, emptyText));
    flow.append(block);
  };
  appendFlowBlock("本任务继承的前序产物", record.inheritedTaskIds, "这是首个任务，没有前序产物。");
  appendFlowBlock("本产物的后续流向", record.forwardedTaskIds, "这是最终任务，没有后续流向。");
  body.append(flow);
}

function selectTask(taskId) {
  state.selectedTaskId = taskId;
  state.userSelectedTask = true;
  state.selectedRoundId = null;
}

function roundsForSelectedTask(rounds) {
  if (!state.selectedTaskId) return rounds;

  const plan = buildTaskPlan(state.events);
  if (!plan) return rounds;

  return rounds.filter((round) => {
    const taskId = taskIdForRound(round);
    return taskId === state.selectedTaskId;
  }).map((round) => {
    const events = round.events.filter(
      (event) => !event.task_id || event.task_id === state.selectedTaskId,
    );
    return enrichRound({ ...round, events });
  });
}

function shouldShowTerminalEvent(plan) {
  if (!plan) return true;
  const lastTask = plan.definitions[plan.definitions.length - 1];
  return Boolean(lastTask && state.selectedTaskId === lastTask.task_id);
}

function taskIdForRound(round) {
  if (!round || !round.events || round.events.length === 0) return null;
  for (const event of round.events) {
    if (event.task_id) {
      return event.task_id;
    }
  }
  return null;
}

function renderRunSummary() {
  const summary = buildRunSummary(state.events);
  const container = document.querySelector("#run-summary");
  container.replaceChildren();

  const items = [
    ["Agentic Loop 轮次", summary.rounds],
    ["模型决策", summary.modelCalls],
    ["工具调用", summary.toolCalls],
    ["上下文构建", summary.contextBuilds],
    ["权限确认", summary.permissions],
  ];

  for (const [label, value] of items) {
    const item = document.createElement("div");
    item.className = "summary-item";

    const valueNode = document.createElement("strong");
    valueNode.className = "summary-value";
    valueNode.textContent = String(value);

    const labelNode = document.createElement("span");
    labelNode.className = "summary-label";
    labelNode.textContent = label;

    item.append(valueNode, labelNode);
    container.append(item);
  }
}

function buildRounds(events) {
  const rounds = [];
  let currentRound = null;
  let loopIndex = 0;

  for (const event of events) {
    if (["run_started", "run_completed", "run_failed", "run_interrupted"].includes(event.phase)) {
      continue;
    }

    if (event.phase === "context_built") {
      loopIndex += 1;
      currentRound = {
        id: `round-${loopIndex}`,
        index: loopIndex,
        title: `第 ${loopIndex} 轮`,
        events: [],
      };
      rounds.push(currentRound);
    }

    if (!currentRound) {
      currentRound = {
        id: "system",
        index: 0,
        title: "系统事件",
        events: [],
      };
      rounds.push(currentRound);
    }

    currentRound.events.push(event);
  }

  return rounds.map(enrichRound);
}

function enrichRound(round) {
  const latest = round.events[round.events.length - 1];
  const decision = round.events.find((event) => event.phase === "llm_decision");
  const toolStarted = round.events.find((event) => event.phase === "tool_started");
  const finalAnswer = round.events.find((event) => event.phase === "final_answer");
  const action = decision?.output?.kind === "final_answer"
    ? "final_answer"
    : toolStarted?.input?.tool_name || finalAnswer?.phase || decision?.output?.tool_name || "观察事件";

  const displaySteps = buildDisplaySteps(round.events);

  return {
    ...round,
    latestStatus: latest?.status || "waiting",
    action,
    eventCount: displaySteps.length,
  };
}

function selectedRound() {
  let rounds = buildRounds(state.events);
  const plan = buildTaskPlan(state.events);
  if (plan && state.selectedTaskId) {
    rounds = roundsForSelectedTask(rounds);
  }
  return rounds.find((round) => round.id === state.selectedRoundId) || rounds[rounds.length - 1] || null;
}

function runStartedEvent() {
  return state.events.find((event) => event.phase === "run_started") || null;
}

function taskEntryEvent(plan) {
  if (plan && state.selectedTaskId) {
    return state.events.find(
      (event) => event.phase === "task_started" && event.task_id === state.selectedTaskId,
    ) || null;
  }
  return runStartedEvent();
}

function terminalEvent() {
  return state.events.find((event) => ["run_completed", "run_failed", "run_interrupted"].includes(event.phase)) || null;
}

function moduleForPhase(phase) {
  const modules = {
    "run_started": "Goal",
    "plan_created": "Task Plan",
    "task_started": "Task Plan",
    "task_completed": "Task Plan",
    "task_failed": "Task Plan",
    "task_skipped": "Task Plan",
    "task_artifact_created": "Task Artifact",
    "task_artifact_missing": "Task Artifact",
    "context_built": "Context",
    "llm_decision": "Model / Reasoning",
    "tool_started": "Tools",
    "tool_finished": "Tools",
    "observation_added": "Memory / State",
    "permission_requested": "Permission",
    "permission_resolved": "Permission",
    "final_answer": "Agent Loop",
    "run_completed": "Agent Loop",
    "run_failed": "Agent Loop",
    "run_interrupted": "Agent Loop",
  };
  return modules[phase] || "Agent Loop";
}

function renderOriginalRequest() {
  const runStarted = state.events.find((event) => event.phase === "run_started");
  const goal = runStarted?.input?.user_goal;
  document.querySelector("#original-request").textContent = goal || "等待任务开始。";
}

function render() {
  renderStatus();
  renderRunSummary();
  renderOriginalRequest();
  renderFinalAnswer();
  renderTaskPlan();
  renderRoundList();
  renderRoundDetail();
}

function renderStatus() {
  document.querySelector("#run-status").textContent = state.status;
  const latest = state.events[state.events.length - 1];
  document.querySelector("#current-title").textContent = latest?.title || "等待任务开始";
}

function renderRoundList() {
  const roundList = document.querySelector("#round-list");
  let rounds = buildRounds(state.events);

  // V0.8: filter by selected task
  const plan = buildTaskPlan(state.events);
  if (plan && state.selectedTaskId) {
    rounds = roundsForSelectedTask(rounds);
  }

  const entry = taskEntryEvent(plan);
  const completion = shouldShowTerminalEvent(plan) ? terminalEvent() : null;
  roundList.replaceChildren();

  if (!entry && rounds.length === 0 && !completion) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "等待 Trace 事件...";
    roundList.append(empty);
    return;
  }

  if (entry) {
    renderTaskEntryItem(roundList, entry);
  }

  for (const round of rounds) {
    const item = document.createElement("li");
    if (round.id === state.selectedRoundId) {
      item.className = "active";
    }

    const button = document.createElement("button");
    button.type = "button";

    const roundIndex = document.createElement("span");
    roundIndex.className = "round-index";
    roundIndex.textContent = String(round.index || "");

    const content = document.createElement("span");
    content.className = "round-content";

    const header = document.createElement("span");
    header.className = "round-header";

    const title = document.createElement("span");
    title.className = "round-title";
    title.textContent = round.title;

    const statusDot = document.createElement("span");
    statusDot.className = `round-status-dot status-${round.latestStatus}`;
    statusDot.setAttribute("aria-hidden", "true");

    header.append(title, statusDot);

    const meta = document.createElement("small");
    meta.textContent = `${round.action} · ${round.latestStatus}`;

    const stepCount = document.createElement("span");
    stepCount.className = "round-step-count";
    stepCount.textContent = `${round.eventCount} 步`;

    content.append(header, meta);

    const badge = document.createElement("span");
    badge.className = "agent-module-badge";
    badge.textContent = "Agentic Loop";

    button.append(roundIndex, content, stepCount, badge);
    button.addEventListener("click", () => {
      state.selectedRoundId = round.id;
      render();
    });

    item.append(button);
    roundList.append(item);
  }

  if (completion) {
    const completionDisplayIndex = rounds.length
      ? rounds[rounds.length - 1].index + 1
      : 1;
    renderTaskCompletionItem(roundList, completion, completionDisplayIndex);
  }
}

function renderTaskEntryItem(roundList, event) {
  const isPlannedTaskEntry = event.phase === "task_started";
  const item = document.createElement("li");
  item.className = "task-entry";
  if (state.selectedRoundId === "task-entry") {
    item.classList.add("active");
  }

  const button = document.createElement("button");
  button.type = "button";

  const roundIndex = document.createElement("span");
  roundIndex.className = "round-index";
  roundIndex.textContent = "0";

  const content = document.createElement("span");
  content.className = "round-content";

  const header = document.createElement("span");
  header.className = "round-header";

  const title = document.createElement("span");
  title.className = "round-title";
  title.textContent = isPlannedTaskEntry ? "任务开始" : "任务入口";

  const statusDot = document.createElement("span");
  statusDot.className = `round-status-dot status-${event.status}`;
  statusDot.setAttribute("aria-hidden", "true");

  header.append(title, statusDot);

  const meta = document.createElement("small");
  meta.textContent = `CLI · ${event.phase} · ${event.status}`;

  const stepCount = document.createElement("span");
  stepCount.className = "round-step-count";
  stepCount.textContent = "1 步";

  content.append(header, meta);

  const badge = document.createElement("span");
  badge.className = "agent-module-badge";
  badge.textContent = isPlannedTaskEntry ? "Task Plan" : "Run Start";

  button.append(roundIndex, content, stepCount, badge);
  button.addEventListener("click", () => {
    state.selectedRoundId = "task-entry";
    render();
  });

  item.append(button);
  roundList.append(item);
}

function renderTaskCompletionItem(roundList, event, displayIndex) {
  const item = document.createElement("li");
  item.className = "task-completion";
  if (state.selectedRoundId === "task-completion") {
    item.classList.add("active");
  }

  const button = document.createElement("button");
  button.type = "button";

  const roundIndex = document.createElement("span");
  roundIndex.className = "round-index";
  roundIndex.textContent = String(displayIndex);

  const content = document.createElement("span");
  content.className = "round-content";

  const header = document.createElement("span");
  header.className = "round-header";

  const title = document.createElement("span");
  title.className = "round-title";
  title.textContent = event.phase === "run_completed" ? "整次运行完成" : "整次运行结束";

  const statusDot = document.createElement("span");
  statusDot.className = `round-status-dot status-${event.status}`;
  statusDot.setAttribute("aria-hidden", "true");

  header.append(title, statusDot);

  const meta = document.createElement("small");
  meta.textContent = `CLI · ${event.phase} · ${event.status}`;

  const stepCount = document.createElement("span");
  stepCount.className = "round-step-count";
  stepCount.textContent = "1 步";

  content.append(header, meta);

  const badge = document.createElement("span");
  badge.className = "agent-module-badge";
  badge.textContent = "Run Completed";

  button.append(roundIndex, content, stepCount, badge);
  button.addEventListener("click", () => {
    state.selectedRoundId = "task-completion";
    render();
  });

  item.append(button);
  roundList.append(item);
}

function renderRoundDetail() {
  const round = selectedRound();
  const detail = document.querySelector("#round-detail");
  detail.replaceChildren();

  if (state.selectedRoundId === "task-entry") {
    renderTaskEntryDetail(detail);
    return;
  }

  if (state.selectedRoundId === "task-completion") {
    const plan = buildTaskPlan(state.events);
    if (shouldShowTerminalEvent(plan)) {
      renderTaskCompletionDetail(detail);
      return;
    }
  }

  if (!round) {
    detail.textContent = "暂无事件。";
    return;
  }

  const displaySteps = buildDisplaySteps(round.events);

  const heading = document.createElement("div");
  heading.className = "detail-heading";

  const title = document.createElement("h3");
  title.textContent = round.title;

  const meta = document.createElement("p");
  meta.className = "detail-meta";
  meta.textContent = `${round.action} · ${round.latestStatus} · ${displaySteps.length} 步`;

  heading.append(title, meta);
  detail.append(heading);
  renderFlowOverview(detail, round.events);

  const steps = document.createElement("div");
  steps.className = "round-steps";
  for (const step of displaySteps) {
    if (step.kind === "command") {
      renderCommandStep(steps, step.startedEvent, step.finishedEvent);
    } else {
      renderEventStep(steps, step.event);
    }
  }
  detail.append(steps);
}

function renderTaskEntryDetail(detail) {
  const event = taskEntryEvent(buildTaskPlan(state.events));
  if (!event) {
    detail.textContent = "暂无任务入口事件。";
    return;
  }
  const isPlannedTaskEntry = event.phase === "task_started";

  const heading = document.createElement("div");
  heading.className = "detail-heading";

  const title = document.createElement("h3");
  title.textContent = isPlannedTaskEntry ? "任务开始" : "任务入口";

  const meta = document.createElement("p");
  meta.className = "detail-meta";
  meta.textContent = `CLI · ${event.phase} · ${event.status} · 1 步`;

  heading.append(title, meta);
  detail.append(heading);
  renderFlowOverview(detail, [event]);

  const steps = document.createElement("div");
  steps.className = "round-steps";
  renderEventStep(steps, event);
  detail.append(steps);
}

function renderTaskCompletionDetail(detail) {
  const event = terminalEvent();
  if (!event) {
    detail.textContent = "暂无任务完成事件。";
    return;
  }

  const heading = document.createElement("div");
  heading.className = "detail-heading";

  const title = document.createElement("h3");
  title.textContent = event.phase === "run_completed" ? "整次运行完成" : "整次运行结束";

  const meta = document.createElement("p");
  meta.className = "detail-meta";
  meta.textContent = `CLI · ${event.phase} · ${event.status} · 1 步`;

  heading.append(title, meta);
  detail.append(heading);
  renderFlowOverview(detail, [event]);

  const steps = document.createElement("div");
  steps.className = "round-steps";
  renderEventStep(steps, event);
  detail.append(steps);
}

function renderFlowOverview(container, events) {
  const flow = document.createElement("section");
  flow.className = "flow-overview";

  const title = document.createElement("h3");
  title.textContent = "本轮流程";

  const nodes = document.createElement("div");
  nodes.className = "flow-nodes";

  for (const item of buildFlowItems(events)) {
    const node = document.createElement("span");
    node.className = "flow-node";
    node.textContent = item;
    nodes.append(node);
  }

  flow.append(title, nodes);
  container.append(flow);
}

function buildFlowItems(events) {
  if (events.some((event) => event.phase === "run_started")) {
    return ["Goal", "CLI", "Run Started"];
  }
  if (events.some((event) => event.phase === "task_started")) {
    return ["Task Plan", "Task Started"];
  }
  if (events.some((event) => event.phase === "run_completed")) {
    return ["Final Answer", "Run Completed"];
  }
  if (events.some((event) => event.phase === "run_failed")) {
    return ["Final Answer", "Run Failed"];
  }
  if (events.some((event) => event.phase === "run_interrupted")) {
    return ["Final Answer", "Run Interrupted"];
  }

  const items = [];
  const add = (label) => {
    if (!items.includes(label)) {
      items.push(label);
    }
  };

  for (const event of events) {
    if (event.phase === "context_built") {
      add("Context Build");
    } else if (event.phase === "llm_decision") {
      add("Model");
    } else if (event.phase === "tool_started") {
      add(`Tool: ${event.input?.tool_name || "unknown"}`);
    } else if (event.phase === "permission_requested") {
      add("Permission Request");
    } else if (event.phase === "permission_resolved") {
      add(event.output?.approved ? "User Approved" : "User Rejected");
    } else if (event.phase === "observation_added") {
      add("Observation");
    } else if (event.phase === "final_answer") {
      add("Final Answer");
    } else if (event.phase === "run_completed") {
      add("Complete");
    } else if (event.phase === "run_failed") {
      add("Failed");
    } else if (event.phase === "run_interrupted") {
      add("Interrupted");
    }
  }

  return items.length > 0 ? items : ["Trace Event"];
}

function createContextSourceCard({source, title, status, statusClass = "", summary, detail}) {
  const card = document.createElement("article");
  card.className = "context-source-card";
  card.dataset.source = source;

  const header = document.createElement("div");
  header.className = "context-source-card-header";
  const heading = document.createElement("h5");
  heading.textContent = title;
  const statusNode = document.createElement("span");
  statusNode.className = `context-source-status ${statusClass}`.trim();
  statusNode.textContent = status;
  header.append(heading, statusNode);

  const summaryNode = document.createElement("p");
  summaryNode.className = "context-source-summary";
  summaryNode.textContent = summary;

  const body = document.createElement("div");
  body.className = "context-source-body";
  body.tabIndex = 0;
  const detailNode = document.createElement("pre");
  detailNode.textContent = typeof detail === "string"
    ? detail
    : JSON.stringify(detail, null, 2);
  body.append(detailNode);

  card.append(header, summaryNode, body);
  return card;
}

function createContextSourceGroup(title, description) {
  const section = document.createElement("section");
  section.className = "context-source-group";
  const header = document.createElement("div");
  header.className = "context-source-group-heading";
  const heading = document.createElement("h4");
  heading.textContent = title;
  const descriptionNode = document.createElement("span");
  descriptionNode.textContent = description;
  header.append(heading, descriptionNode);
  const grid = document.createElement("div");
  grid.className = "context-source-grid";
  section.append(header, grid);
  return {section, grid};
}

function selectedProjectPath(entry) {
  if (typeof entry === "object" && entry !== null) {
    return typeof entry.path === "string" ? entry.path : "";
  }
  return typeof entry === "string" ? entry : "";
}

function buildSelectedProjectContentText(output) {
  const entries = output.selected_project_content || [];
  if (entries.length === 0) {
    return "暂无已读取的项目文件";
  }

  const observations = output.observations || [];
  return entries.map((entry) => {
    const path = selectedProjectPath(entry);
    let content = "";
    for (let index = observations.length - 1; index >= 0; index -= 1) {
      const observation = observations[index];
      if (
        observation.tool_name === "read_file"
        && observation.args?.path === path
        && observation.result?.success === true
        && typeof observation.result?.content === "string"
      ) {
        content = observation.result?.content;
        break;
      }
    }
    const displayedContent = content || "未找到对应的成功 read_file observation";
    return `${path}\n${"-".repeat(path.length)}\n${displayedContent}`;
  }).join("\n\n");
}

function buildContextChange(event, allEvents) {
  const snapshots = allEvents
    .filter((item) => item.phase === "context_built" && item.step < event.step)
    .sort((a, b) => a.step - b.step);
  const previous = snapshots[snapshots.length - 1];
  if (!previous) {
    return ["首轮，无前序上下文"];
  }

  const currentObservations = event.output?.observations || [];
  const previousObservations = previous.output?.observations || [];

  // 正常记录使用路径字符串；同时兼容开发期生成的 {path, preview} 旧条目
  const currentFiles = (event.output?.selected_project_content || []);
  const previousEntries = (previous.output?.selected_project_content || []);
  const previousPaths = new Set(
    previousEntries.map(selectedProjectPath)
  );
  const addedFiles = currentFiles
    .map(selectedProjectPath)
    .filter((path) => path && !previousPaths.has(path));

  const changes = [];
  if (currentObservations.length > previousObservations.length) {
    changes.push(`新增 ${currentObservations.length - previousObservations.length} 条 observation`);
  }
  if (addedFiles.length > 0) {
    changes.push(`新增已读取文件：${addedFiles.join(", ")}`);
  }
  return changes.length > 0 ? changes : ["与上一轮相比无新增动态上下文"];
}

function renderContextBuiltStep(container, event, allEvents) {
  const output = event.output || {};

  const intro = document.createElement("section");
  intro.className = "context-build-intro";
  const introCopy = document.createElement("div");
  const introTitle = document.createElement("h4");
  introTitle.textContent = "本轮模型将使用 7 类上下文";
  const introDescription = document.createElement("p");
  introDescription.textContent = "每个来源独立展示；卡片内容可单独上下滚动，看到的就是本轮判断前实际加入的上下文。";
  introCopy.append(introTitle, introDescription);
  const sourceCount = document.createElement("span");
  sourceCount.className = "context-source-count";
  sourceCount.textContent = "5 类基础 · 2 类动态";
  intro.append(introCopy, sourceCount);

  const base = createContextSourceGroup(
    "运行级基础上下文 · 本轮沿用",
    "运行开始时加载一次，每轮继续提供给模型",
  );
  const wsConfig = output.workspace_config || {};
  let wsStatus = "未加载";
  let wsStatusClass = "";
  if (wsConfig.status === "loaded") {
    wsStatus = wsConfig.truncated ? "已截断" : "已加载";
    wsStatusClass = "loaded";
  } else if (wsConfig.status === "error") {
    wsStatus = "读取错误";
  }

  const runMemory = output.run_memory || {};
  const memStatus = (runMemory.status === "loaded" && runMemory.summary_count > 0)
    ? `${runMemory.summary_count} 条历史`
    : "暂无可用历史摘要";

  base.grid.append(
    createContextSourceCard({
      source: "goal",
      title: "当前用户目标",
      status: "最高优先级",
      statusClass: "priority",
      summary: "用户本次明确输入，其他上下文只能辅助理解，不能覆盖这个目标。",
      detail: output.user_goal || "",
    }),
    createContextSourceCard({
      source: "workspace-config",
      title: "Workspace Config · minagent.md",
      status: wsStatus,
      statusClass: wsStatusClass,
      summary: "来自 workspace 根目录的规则和偏好，不改变本地权限边界。",
      detail: wsConfig.status ? wsConfig : null,
    }),
    createContextSourceCard({
      source: "run-memory",
      title: "最近运行摘要",
      status: memStatus,
      summary: "只读取当前 workspace 最近的有效记录，作为辅助背景。",
      detail: Object.keys(runMemory).length > 0 ? runMemory : {status: "empty", summaries: []},
    }),
    createContextSourceCard({
      source: "run-metadata",
      title: "运行元信息",
      status: "本轮沿用",
      summary: "帮助解释这次运行环境，不会直接触发任何工具。",
      detail: output.run_metadata || null,
    }),
    createContextSourceCard({
      source: "tool-catalog",
      title: "工具目录",
      status: "含权限边界",
      statusClass: "permission",
      summary: "模型只能提出这些本地动作，工具执行仍由 ToolRegistry 控制。",
      detail: output.tool_catalog || [],
    }),
  );

  const dynamic = createContextSourceGroup(
    "逐轮动态上下文 · 截至本轮",
    "工具结果只影响下一轮及后续判断",
  );
  const change = document.createElement("div");
  change.className = "context-change";
  change.textContent = buildContextChange(event, allEvents).join("；");
  dynamic.section.insertBefore(change, dynamic.grid);
  const spcEntries = output.selected_project_content || [];
  const spcText = buildSelectedProjectContentText(output);

  dynamic.grid.append(
    createContextSourceCard({
      source: "observations",
      title: "Working Observations",
      status: `${(output.observations || []).length} 条 · 本轮动态`,
      summary: "Agent 已经获得的真实工具结果，是下一步判断的工作状态。",
      detail: output.observations || [],
    }),
    createContextSourceCard({
      source: "project-content",
      title: "Selected Project Content",
      status: `${spcEntries.length} files`,
      summary: "通过 read_file 进入上下文的任务材料，与 minagent.md 配置分开。",
      detail: spcText,
    }),
  );

  const raw = document.createElement("details");
  raw.className = "raw-context";
  const rawSummary = document.createElement("summary");
  rawSummary.textContent = "原始 Context JSON · 调试信息（默认折叠）";
  const rawPre = document.createElement("pre");
  rawPre.textContent = JSON.stringify(output, null, 2);
  raw.append(rawSummary, rawPre);

  container.append(intro, base.section, dynamic.section, raw);
}

function renderEventStep(container, event) {
  const step = document.createElement("section");
  step.className = "event-step";

  const header = document.createElement("div");
  header.className = "event-step-header";

  const number = document.createElement("span");
  number.className = "event-step-number";
  number.textContent = String(event.step);

  const heading = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = event.title;

  const meta = document.createElement("p");
  meta.className = "detail-meta";
  meta.textContent = `${moduleForPhase(event.phase)} · ${event.phase} · ${event.status}`;

  heading.append(title, meta);
  header.append(number, heading);
  step.append(header);

  if (event.reason) {
    appendSection(step, "为什么发生", event.reason);
  }

  if (event.phase === "context_built") {
    renderContextBuiltStep(step, event, state.events);
    container.append(step);
    return;
  }

  if (event.phase === "llm_decision") {
    renderModelDecisionStep(step, event);
  } else {
    const ioGrid = document.createElement("div");
    ioGrid.className = "step-io-grid";
    appendSection(ioGrid, "输入", event.input);
    appendSection(ioGrid, "输出", event.output);
    step.append(ioGrid);
  }

  appendSection(step, "原始事件 JSON", event, "raw-event");
  container.append(step);
}

function renderModelDecisionStep(container, event) {
  const modelCall = event.output?.metadata?.model_call;
  const section = appendSectionShell(container, "模型决策");

  if (!modelCall) {
    const empty = document.createElement("p");
    empty.className = "model-call-empty";
    empty.textContent = "未调用大模型：当前使用 FakeLLM 本地决策器。";
    section.append(empty);
  } else {
    const badge = document.createElement("p");
    badge.className = "model-call-badge";
    badge.textContent = `已调用大模型：${modelCall.provider || "unknown"} / ${modelCall.model || "unknown"}`;
    section.append(badge);

    const request = modelCall.request || {};
    appendCodeBlock(section, "System Prompt", request.system_prompt || "");
    appendCodeBlock(section, "User Prompt", request.user_prompt || "");

    const response = modelCall.response || {};
    appendCodeBlock(section, "大模型返回 message.content", response.content || response.error || "");
  }

  renderDecision(section, event.output);
}

function renderDecision(container, output) {
  const decision = {
    kind: output?.kind,
    tool_name: output?.tool_name,
    args: output?.args,
    reason: output?.reason,
    message: output?.message,
    success: output?.success,
  };
  appendSection(container, "解析后的决策", compactObject(decision));
}

function appendSection(container, title, value, extraClassName = "") {
  const section = appendSectionShell(container, title);
  if (extraClassName) {
    section.classList.add(extraClassName);
  }
  appendPre(section, formatValue(value));
  return section;
}

function appendSectionShell(container, title) {
  const section = document.createElement("section");
  section.className = "detail-section";

  const heading = document.createElement("h3");
  heading.textContent = title;

  section.append(heading);
  container.append(section);
  return section;
}

function appendCodeBlock(container, title, value) {
  const label = document.createElement("h4");
  label.textContent = title;
  container.append(label);
  appendPre(container, value || "无内容");
}

function appendPre(container, text) {
  const pre = document.createElement("pre");
  pre.textContent = text;
  container.append(pre);
}

function formatValue(value) {
  if (typeof value === "string") {
    return value || "无内容";
  }
  if (value === null || value === undefined) {
    return "无内容";
  }
  if (typeof value === "object" && Object.keys(value).length === 0) {
    return "无内容";
  }
  return JSON.stringify(value, null, 2);
}

function compactObject(value) {
  return Object.fromEntries(Object.entries(value).filter((entry) => entry[1] !== undefined && entry[1] !== null));
}

function renderFinalAnswer() {
  const finalEvent = state.events.find((event) => event.phase === "final_answer");
  document.querySelector("#final-answer").textContent =
    finalEvent?.output?.message || "任务完成后展示最终回答。";
}

// ---- V0.7: command step display ----

function isRunCommandStart(event) {
  return event.phase === "tool_started" && event.input?.tool_name === "run_command";
}

function buildDisplaySteps(events) {
  const steps = [];
  let index = 0;
  while (index < events.length) {
    const event = events[index];
    if (isRunCommandStart(event)) {
      const nextEvent = events[index + 1];
      const finishedEvent = (nextEvent && nextEvent.phase === "tool_finished") ? nextEvent : null;
      steps.push({ kind: "command", startedEvent: event, finishedEvent: finishedEvent });
      index += finishedEvent ? 2 : 1;
    } else {
      steps.push({ kind: "event", event: event });
      index += 1;
    }
  }
  return steps;
}

function renderCommandStep(container, startedEvent, finishedEvent) {
  const step = document.createElement("section");
  step.className = "event-step command-step";

  const header = document.createElement("div");
  header.className = "event-step-header";

  const number = document.createElement("span");
  number.className = "event-step-number";
  number.textContent = String(startedEvent.step);

  const heading = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = startedEvent.title;

  const label = document.createElement("span");
  label.className = "command-label";
  label.textContent = ">_ COMMAND";

  const meta = document.createElement("p");
  meta.className = "detail-meta";
  meta.textContent = `${moduleForPhase(startedEvent.phase)} · ${startedEvent.phase} · ${startedEvent.status}`;

  heading.append(title, label);
  header.append(number, heading);
  step.append(header);
  step.append(meta);

  if (startedEvent.reason) {
    appendSection(step, "为什么发生", startedEvent.reason);
  }

  // Build command input details
  const inputDetails = {};
  const metadata = finishedEvent?.output?.metadata || {};
  if (metadata.command_id) {
    inputDetails["预定义动作"] = metadata.command_id;
  }
  if (metadata.display_command) {
    inputDetails["实际命令"] = metadata.display_command;
  }
  inputDetails["工作目录"] = metadata.workspace || "(unknown)";

  // Build command output details
  const outputDetails = {};
  if (finishedEvent) {
    outputDetails["stdout"] = metadata.stdout || "(empty)";
    outputDetails["stderr"] = metadata.stderr || "(empty)";
    outputDetails["exit_code"] = metadata.exit_code != null ? String(metadata.exit_code) : "N/A";
    outputDetails["duration"] = metadata.duration_ms != null ? `${metadata.duration_ms} ms` : "N/A";
    outputDetails["truncated"] = (metadata.stdout_truncated || metadata.stderr_truncated) ? "true" : "false";
  } else {
    outputDetails["status"] = "等待执行完成...";
  }

  const ioGrid = document.createElement("div");
  ioGrid.className = "step-io-grid";
  appendSection(ioGrid, "输入", inputDetails);
  appendSection(ioGrid, "输出", outputDetails);
  step.append(ioGrid);

  // Raw event details for both events
  const rawSection = appendSectionShell(step, "原始事件 JSON");
  rawSection.classList.add("raw-event");
  const rawPre = document.createElement("pre");
  const rawData = finishedEvent
    ? [startedEvent, finishedEvent]
    : [startedEvent];
  rawPre.textContent = JSON.stringify(rawData, null, 2);
  rawSection.append(rawPre);

  container.append(step);
}

render();
connectTraceStream();
