(() => {
  const state = {
    service: null,
    currentRun: null,
    activeRoute: "new",
    selectedHistoryId: null,
    historyRows: [],
    pendingPermission: null,
    currentEventSource: null,
    viewingHistoricalRunId: null,
    lastFocusedElement: null,
  };
  let viewer;
  const $ = (id) => document.getElementById(id);

  async function apiFetch(path, options = {}) {
    const response = await fetch(path, options);
    let envelope;
    try {
      envelope = await response.json();
    } catch {
      throw new Error("服务返回了无法识别的响应");
    }
    if (!response.ok || !envelope.ok) {
      throw new Error(envelope?.error?.message || "请求未完成");
    }
    return envelope.data;
  }

  function parseRoute() {
    const parts = location.hash.replace(/^#\//, "").split("/").filter(Boolean);
    if (parts[0] === "trace" && parts[1]) return { name: "trace", runId: parts[1] };
    if (["new", "trace", "history"].includes(parts[0])) return { name: parts[0], runId: null };
    return { name: "new", runId: null };
  }

  function renderRoute(name) {
    state.activeRoute = name;
    document.querySelectorAll("[data-page]").forEach((page) => {
      page.hidden = page.dataset.page !== name;
    });
    document.querySelectorAll(".app-nav [data-route]").forEach((button) => {
      button.classList.toggle("active", button.dataset.route === name);
    });
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  async function route(route = parseRoute()) {
    const { name, runId } = route;
    if (!location.hash || parseRoute().name !== name || parseRoute().runId !== runId) {
      location.hash = runId ? `#/trace/${runId}` : `#/${name}`;
    }
    renderRoute(name);
    if (name === "history") {
      await loadHistory();
      return;
    }
    if (name === "trace" && runId) {
      await loadHistoricalRun(runId);
      return;
    }
    if (name === "trace") {
      state.viewingHistoricalRunId = null;
      if (state.currentRun) renderRun(state.currentRun, false);
    }
  }

  function renderRun(run, historical) {
    viewer.loadRun({ runId: run.run_id, status: run.status, events: run.events || [] });
    $("request-model").textContent = displayModel(run.decision_model);
    $("request-workspace").textContent = run.workspace;
  }

  function updateLaunchState() {
    const deepseek = $("model-deepseek").checked;
    const deepseekActive = Boolean(state.currentRun?.active && state.currentRun.decision_model === "deepseek");
    $("key-panel").hidden = !deepseek;
    $("key-input-row").hidden = Boolean(state.service?.configured);
    $("configured-key-row").hidden = !state.service?.configured;
    $("key-status-text").textContent = state.service?.configured ? "本次服务已配置" : "未配置";
    $("configure-key").disabled = deepseekActive;
    $("clear-key").disabled = deepseekActive;
    $("goal-count").textContent = `${$("goal-input").value.length} / 1000`;
    $("start-run").disabled = !$("goal-input").value.trim() || Boolean(state.currentRun?.active) || (deepseek && !state.service?.configured);
  }

  function renderServiceState() {
    $("workspace-value").textContent = state.service.workspace;
    const active = Boolean(state.currentRun?.active);
    const waiting = state.service.service_state === "approval_required";
    $("service-status").textContent = waiting ? "Approval" : active ? "Busy" : "Ready";
    $("service-status").className = `status-pill ${waiting ? "permission" : active ? "running" : ""}`;
    $("current-run-card").hidden = !active;
    $("current-run-goal").textContent = active ? state.currentRun.user_goal : "";
    $("current-run-status").textContent = waiting ? "Needs approval" : active ? "Running" : "Ready";
    $("current-run-status").className = `status-pill ${waiting ? "permission" : active ? "running" : ""}`;
    $("nav-run-dot").className = `run-dot ${waiting ? "permission" : active ? "running" : ""}`;
    updateLaunchState();
  }

  function updateCurrentRun(event) {
    const existing = state.currentRun.events.findIndex((item) => item.step === event.step);
    if (existing >= 0) state.currentRun.events[existing] = event;
    else state.currentRun.events.push(event);
    state.currentRun.status = event.status || state.currentRun.status;
    state.currentRun.active = !["run_completed", "run_failed", "run_interrupted"].includes(event.phase);
  }

  function connectCurrentRun(run) {
    state.currentEventSource?.close();
    state.currentEventSource = null;
    if (!run?.active) return;
    const stream = new EventSource(`/api/runs/current/events?run_id=${encodeURIComponent(run.run_id)}`);
    state.currentEventSource = stream;
    stream.onopen = () => {
      if (state.service) $("service-status").textContent = state.service.service_state;
    };
    stream.onmessage = (message) => {
      const event = JSON.parse(message.data);
      if (!state.currentRun || event.run_id !== state.currentRun.run_id) return;
      updateCurrentRun(event);
      if (!state.viewingHistoricalRunId && state.activeRoute === "trace") viewer.applyEvent(event);
      if (event.phase === "permission_requested") refreshPendingPermission(true);
      if (event.phase === "permission_resolved") refreshPendingPermission(false);
      if (["run_completed", "run_failed", "run_interrupted"].includes(event.phase)) {
        stream.close();
        state.currentEventSource = null;
        bootstrap().catch(showError);
      }
      updateLaunchState();
    };
    stream.onerror = () => {
      if (state.currentRun?.active) $("service-status").textContent = "连接重连中";
    };
  }

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
  async function refreshPendingPermission(openDrawer, retries = [50, 100, 200, 400, 800]) {
    const pending = await apiFetch("/api/permissions/current");
    state.pendingPermission = pending;
    $("pending-permission-button").hidden = !pending;
    if (pending && openDrawer) openPermissionDrawer();
    if (!pending) closePermissionDrawer();
    if (!pending && openDrawer && state.currentRun?.active && retries.length) {
      await delay(retries[0]);
      if (state.currentRun?.active && !state.pendingPermission) return refreshPendingPermission(openDrawer, retries.slice(1));
    }
  }

  function openPermissionDrawer() {
    const pending = state.pendingPermission;
    if (!pending) return;
    state.lastFocusedElement = document.activeElement;
    $("permission-drawer").removeAttribute("inert");
    $("permission-drawer").setAttribute("aria-hidden", "false");
    $("permission-title").textContent = `允许执行 ${pending.tool_name}？`;
    $("permission-run").textContent = pending.run_id;
    $("permission-tool").textContent = pending.tool_name;
    $("permission-reason").textContent = pending.reason || "";
    $("permission-workspace").textContent = pending.workspace || "";
    $("permission-target").textContent = pending.path || pending.command || pending.command_id || "";
    $("permission-preview").textContent = pending.preview || "";
    $("permission-risk").textContent = pending.risk || "";
    $("approve-permission").focus();
  }

  function closePermissionDrawer() {
    $("permission-drawer").setAttribute("aria-hidden", "true");
    $("permission-drawer").setAttribute("inert", "");
    if (state.lastFocusedElement?.isConnected) state.lastFocusedElement.focus();
  }

  async function resolvePermission(approved) {
    const pending = state.pendingPermission;
    if (!pending) return;
    $("approve-permission").disabled = true;
    $("reject-permission").disabled = true;
    try {
      await apiFetch(`/api/permissions/${pending.permission_id}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Origin: location.origin },
        body: JSON.stringify({ approved }),
      });
    } catch (error) {
      if (!/already resolved/.test(error.message)) throw error;
    } finally {
      $("approve-permission").disabled = false;
      $("reject-permission").disabled = false;
      await refreshPendingPermission(false);
    }
  }

  async function loadHistory() {
    const data = await apiFetch("/api/history");
    state.historyRows = data.runs;
    const list = $("history-list");
    list.replaceChildren();
    data.runs.forEach((row) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      const meta = document.createElement("span");
      const title = document.createElement("h3");
      const copy = document.createElement("p");
      button.className = "history-item";
      button.type = "button";
      button.dataset.historyId = row.run_id;
      meta.className = "history-meta";
      const created = document.createElement("span");
      created.textContent = row.created_at || "—";
      const status = document.createElement("span");
      status.textContent = row.status;
      meta.append(created, status);
      title.textContent = row.goal;
      copy.textContent = `${displayModel(row.decision_model)} · 已保存运行`;
      button.append(meta, title, copy);
      button.addEventListener("click", () => selectHistory(row).catch(showError));
      item.append(button);
      list.append(item);
    });
    if (state.selectedHistoryId) {
      const selected = data.runs.find((row) => row.run_id === state.selectedHistoryId);
      if (selected) selectHistory(selected).catch(showError);
    }
  }

  function taskProgress(record) {
    const plan = record.events?.find((event) => event.phase === "plan_created")?.output?.tasks || [];
    if (!plan.length) return "—";
    const completed = record.events.filter((event) => event.phase === "task_completed").length;
    return `${completed} / ${plan.length}`;
  }

  function displayModel(model) {
    if (model === "deepseek") return "DeepSeek";
    if (model === "fake") return "Fake";
    return "Unknown";
  }

  async function selectHistory(row) {
    state.selectedHistoryId = row.run_id;
    document.querySelectorAll("[data-history-id]").forEach((button) => {
      button.classList.toggle("selected", button.dataset.historyId === row.run_id);
    });
    $("history-title").textContent = row.goal;
    $("history-description").textContent = "正在加载这份已保存运行的只读概要。";
    $("history-model").textContent = displayModel(row.decision_model);
    $("history-status").textContent = row.status;
    $("history-tasks").textContent = "—";
    $("replay-run").disabled = true;
    const record = await apiFetch(`/api/history/${encodeURIComponent(row.run_id)}`);
    if (state.selectedHistoryId !== row.run_id) return;
    const answer = [...(record.events || [])].reverse().find((event) => event.phase === "final_answer")?.output?.message;
    $("history-description").textContent = answer || "该运行没有可展示的最终回答。";
    $("history-model").textContent = displayModel(record.decision_model);
    $("history-status").textContent = record.status;
    $("history-tasks").textContent = taskProgress(record);
    $("replay-run").disabled = false;
  }

  async function loadHistoricalRun(runId) {
    const record = await apiFetch(`/api/history/${encodeURIComponent(runId)}`);
    state.selectedHistoryId = runId;
    state.viewingHistoricalRunId = runId;
    renderRun(record, true);
    $("history-title").textContent = record.user_goal;
    $("history-model").textContent = displayModel(record.decision_model);
    $("history-status").textContent = record.status;
    $("history-tasks").textContent = taskProgress(record);
  }

  async function bootstrap() {
    state.service = await apiFetch("/api/state");
    state.currentRun = state.service.current_run;
    renderServiceState();
    await refreshPendingPermission(false);
    connectCurrentRun(state.currentRun);
    await route();
  }

  function showError(error) {
    $("service-status").textContent = error.message || "操作未完成";
  }

  document.querySelectorAll("[data-route]").forEach((button) => {
    button.addEventListener("click", () => route({ name: button.dataset.route, runId: null }).catch(showError));
  });
  $("goal-input").addEventListener("input", updateLaunchState);
  document.querySelectorAll("input[name=model]").forEach((input) => input.addEventListener("change", updateLaunchState));
  document.querySelectorAll("[data-preset-goal]").forEach((button) => {
    button.addEventListener("click", () => {
      $("goal-input").value = button.dataset.presetGoal || "";
      updateLaunchState();
      $("goal-input").focus();
    });
  });
  $("configure-key").addEventListener("click", async () => {
    try {
      await apiFetch("/api/deepseek-key", { method: "PUT", headers: { "Content-Type": "application/json", Origin: location.origin }, body: JSON.stringify({ api_key: $("deepseek-key").value }) });
    } finally {
      $("deepseek-key").value = "";
    }
    await bootstrap();
  });
  $("clear-key").addEventListener("click", async () => { await apiFetch("/api/deepseek-key", { method: "DELETE", headers: { Origin: location.origin } }); await bootstrap(); });
  $("replay-run").addEventListener("click", () => {
    if (state.selectedHistoryId) route({ name: "trace", runId: state.selectedHistoryId }).catch(showError);
  });
  $("start-run").addEventListener("click", async () => {
    const run = await apiFetch("/api/runs", { method: "POST", headers: { "Content-Type": "application/json", Origin: location.origin }, body: JSON.stringify({ goal: $("goal-input").value.trim(), decision_model: $("model-deepseek").checked ? "deepseek" : "fake" }) });
    state.currentRun = run;
    state.viewingHistoricalRunId = null;
    renderServiceState();
    connectCurrentRun(run);
    await route({ name: "trace", runId: null });
  });
  $("pending-permission-button").addEventListener("click", openPermissionDrawer);
  $("close-permission").addEventListener("click", closePermissionDrawer);
  $("approve-permission").addEventListener("click", () => resolvePermission(true).catch(showError));
  $("reject-permission").addEventListener("click", () => resolvePermission(false).catch(showError));
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closePermissionDrawer(); });
  window.addEventListener("hashchange", () => route().catch(showError));
  viewer = window.MinAgentTraceViewer.create({ root: document.querySelector("[data-trace-viewer-root]") });
  bootstrap().catch(showError);
})();
