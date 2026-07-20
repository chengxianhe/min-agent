(() => {
  const HISTORY_BATCH_SIZE = 20;
  const TRANSIENT_MESSAGE_DURATION_MS = 3000;
  const state = {
    service: null,
    currentRun: null,
    activeRoute: "new",
    selectedHistoryId: null,
    historyRows: [],
    historyVisibleCount: HISTORY_BATCH_SIZE,
    pendingPermission: null,
    currentEventSource: null,
    viewingHistoricalRunId: null,
    lastFocusedElement: null,
    keyPending: false,
    runPending: false,
    messageTimer: null,
  };
  let viewer;
  const $ = (id) => document.getElementById(id);
  const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
  const numberFormatter = new Intl.NumberFormat("zh-CN");

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

  function cancelMessageTimer() {
    if (state.messageTimer === null) return;
    clearTimeout(state.messageTimer);
    state.messageTimer = null;
  }

  function clearMessage() {
    cancelMessageTimer();
    const target = $("app-message");
    target.hidden = true;
    target.textContent = "";
    delete target.dataset.tone;
  }

  function showTransientMessage(message) {
    cancelMessageTimer();
    const target = $("app-message");
    target.textContent = message;
    target.dataset.tone = "success";
    target.hidden = false;
    state.messageTimer = window.setTimeout(() => {
      state.messageTimer = null;
      target.hidden = true;
      target.textContent = "";
      delete target.dataset.tone;
    }, TRANSIENT_MESSAGE_DURATION_MS);
  }

  function showError(error, nextStep = "请检查当前输入和服务状态后重试。") {
    cancelMessageTimer();
    const message = error?.message || "操作未完成";
    const target = $("app-message");
    target.textContent = message + " " + nextStep;
    target.dataset.tone = "error";
    target.hidden = false;
  }

  function setFieldError(id, message = "") {
    const target = $(id);
    target.textContent = message;
    target.hidden = !message;
  }

  function renderRoute(name) {
    state.activeRoute = name;
    document.querySelectorAll("[data-page]").forEach((page) => {
      page.hidden = page.dataset.page !== name;
    });
    document.querySelectorAll(".app-nav [data-route]").forEach((link) => {
      const active = link.dataset.route === name;
      link.classList.toggle("active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    $("skip-link").href = "#" + name + "-page";
    const pageName = name === "new" ? "发起任务" : name === "trace" ? "过程查看" : "历史运行";
    document.title = pageName + " · Min Agent";
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  async function route(route = parseRoute()) {
    const { name, runId } = route;
    if (!location.hash || parseRoute().name !== name || parseRoute().runId !== runId) {
      location.hash = runId ? "#/trace/" + runId : "#/" + name;
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
      else viewer.reset();
    }
  }

  function renderRun(run, historical) {
    viewer.loadRun({ runId: run.run_id, status: run.status, events: run.events || [] });
    $("request-model").textContent = displayModel(run.decision_model);
    $("request-workspace").textContent = run.workspace;
    $("trace-page").dataset.viewMode = historical ? "history" : "current";
  }

  function updateLaunchState() {
    const deepseek = $("model-deepseek").checked;
    const deepseekActive = Boolean(state.currentRun?.active && state.currentRun.decision_model === "deepseek");
    const configured = Boolean(state.service?.configured);
    const goal = $("goal-input").value.trim();

    $("key-panel").hidden = !deepseek;
    $("key-input-row").hidden = configured;
    $("configured-key-row").hidden = !configured;
    $("key-status-text").textContent = configured ? "本次服务已配置" : "未配置";
    $("configure-key").disabled = state.keyPending || deepseekActive;
    $("clear-key").disabled = state.keyPending || deepseekActive;
    $("configure-key").textContent = state.keyPending ? "正在保存…" : "保存到本次服务";
    $("goal-count").textContent = $("goal-input").value.length + " / 1000";
    $("start-run").disabled =
      state.runPending ||
      !goal ||
      Boolean(state.currentRun?.active) ||
      (deepseek && !configured);
    $("start-run").textContent = state.runPending ? "正在启动…" : "开始运行 →";
  }

  function renderServiceState() {
    $("workspace-value").textContent = state.service.workspace;
    const active = Boolean(state.currentRun?.active);
    const waiting = state.service.service_state === "approval_required";
    $("service-status").textContent = waiting ? "Approval" : active ? "Busy" : "Ready";
    $("service-status").className = "status-pill " + (waiting ? "permission" : active ? "running" : "");
    $("current-run-card").hidden = !active;
    $("current-run-goal").textContent = active ? state.currentRun.user_goal : "";
    $("current-run-status").textContent = waiting ? "Needs approval" : active ? "Running" : "Ready";
    $("current-run-status").className = "status-pill " + (waiting ? "permission" : active ? "running" : "");
    $("nav-run-dot").className = "run-dot " + (waiting ? "permission" : active ? "running" : "");
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
    const stream = new EventSource("/api/runs/current/events?run_id=" + encodeURIComponent(run.run_id));
    state.currentEventSource = stream;
    stream.onopen = () => {
      if (state.service) $("service-status").textContent = "Connected";
    };
    stream.onmessage = (message) => {
      let event;
      try {
        event = JSON.parse(message.data);
      } catch {
        showError(new Error("收到无法识别的运行事件"), "页面会保留当前状态；请刷新后重试。");
        return;
      }
      if (!state.currentRun || event.run_id !== state.currentRun.run_id) return;
      updateCurrentRun(event);
      if (!state.viewingHistoricalRunId && state.activeRoute === "trace") viewer.applyEvent(event);
      if (event.phase === "permission_requested") refreshPendingPermission(true).catch(showError);
      if (event.phase === "permission_resolved") refreshPendingPermission(false).catch(showError);
      if (["run_completed", "run_failed", "run_interrupted"].includes(event.phase)) {
        stream.close();
        state.currentEventSource = null;
        bootstrap().catch(showError);
      }
      updateLaunchState();
    };
    stream.onerror = () => {
      if (state.currentRun?.active) $("service-status").textContent = "Reconnecting…";
    };
  }

  const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

  async function refreshPendingPermission(openDrawer, retries = [50, 100, 200, 400, 800]) {
    const pending = await apiFetch("/api/permissions/current");
    state.pendingPermission = pending;
    $("pending-permission-button").hidden = !pending;
    const drawerOpen = $("permission-drawer").getAttribute("aria-hidden") === "false";
    $("pending-permission-button").setAttribute("aria-expanded", pending && drawerOpen ? "true" : "false");
    if (pending && openDrawer) openPermissionDrawer();
    if (!pending) closePermissionDrawer();
    if (!pending && openDrawer && state.currentRun?.active && retries.length) {
      await delay(retries[0]);
      if (state.currentRun?.active && !state.pendingPermission) {
        return refreshPendingPermission(openDrawer, retries.slice(1));
      }
    }
  }

  function setBackgroundInert(inert) {
    document.querySelectorAll(".app-header, #app-message, [data-page]").forEach((element) => {
      if (inert) element.setAttribute("inert", "");
      else element.removeAttribute("inert");
    });
  }

  function permissionFocusableElements() {
    return Array.from(
      $("permission-drawer").querySelectorAll(
        'button:not([disabled]), a[href], input:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    ).filter((element) => !element.hidden);
  }

  function openPermissionDrawer() {
    const pending = state.pendingPermission;
    if (!pending) return;
    clearMessage();
    state.lastFocusedElement = document.activeElement;
    setBackgroundInert(true);
    $("permission-drawer").removeAttribute("inert");
    $("permission-drawer").setAttribute("aria-hidden", "false");
    $("pending-permission-button").setAttribute("aria-expanded", "true");
    $("permission-title").textContent = "允许执行 " + pending.tool_name + "？";
    $("permission-run").textContent = pending.run_id;
    $("permission-tool").textContent = pending.tool_name;
    $("permission-reason").textContent = pending.reason || "运行时未提供原因。";
    $("permission-workspace").textContent = pending.workspace || "当前固定 workspace";
    $("permission-target").textContent = pending.path || pending.command || pending.command_id || "无目标信息";
    $("permission-preview").textContent = pending.preview || "没有可展示的内容预览。";
    $("permission-risk").textContent = pending.risk || "请确认该动作符合当前目标。";
    $("close-permission").focus();
  }

  function closePermissionDrawer() {
    const drawer = $("permission-drawer");
    const wasOpen = drawer.getAttribute("aria-hidden") === "false";
    drawer.setAttribute("aria-hidden", "true");
    drawer.setAttribute("inert", "");
    $("pending-permission-button").setAttribute("aria-expanded", "false");
    setBackgroundInert(false);
    if (wasOpen && state.lastFocusedElement?.isConnected) state.lastFocusedElement.focus();
    state.lastFocusedElement = null;
  }

  function trapPermissionFocus(event) {
    if (event.key !== "Tab" || $("permission-drawer").getAttribute("aria-hidden") !== "false") return;
    const focusable = permissionFocusableElements();
    if (!focusable.length) {
      event.preventDefault();
      $("permission-drawer").focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function resolvePermission(approved) {
    const pending = state.pendingPermission;
    if (!pending) return;
    const approveButton = $("approve-permission");
    const rejectButton = $("reject-permission");
    const previousApproveText = approveButton.textContent;
    const previousRejectText = rejectButton.textContent;
    approveButton.disabled = true;
    rejectButton.disabled = true;
    (approved ? approveButton : rejectButton).textContent = "处理中…";
    try {
      await apiFetch("/api/permissions/" + pending.permission_id + "/decision", {
        method: "POST",
        headers: { "Content-Type": "application/json", Origin: location.origin },
        body: JSON.stringify({ approved }),
      });
      showTransientMessage(approved ? "已批准本次执行，Agent 将继续运行。" : "已拒绝本次执行，Agent 将按既有规则收敛。");
    } catch (error) {
      if (!/already resolved/.test(error.message)) throw error;
    } finally {
      approveButton.textContent = previousApproveText;
      rejectButton.textContent = previousRejectText;
      approveButton.disabled = false;
      rejectButton.disabled = false;
      await refreshPendingPermission(false);
    }
  }

  function formatDate(value) {
    if (!value) return "时间未知";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return dateFormatter.format(date);
  }

  function displayStatus(status) {
    if (status === "completed") return "已完成";
    if (status === "failed") return "失败";
    if (status === "running") return "运行中";
    if (status === "interrupted") return "已中断";
    return status || "状态未知";
  }

  function createHistoryItem(row) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    const meta = document.createElement("span");
    const title = document.createElement("h3");
    const copy = document.createElement("p");
    const created = document.createElement("span");
    const status = document.createElement("span");

    button.className = "history-item";
    button.type = "button";
    button.dataset.historyId = row.run_id;
    button.setAttribute("aria-pressed", row.run_id === state.selectedHistoryId ? "true" : "false");
    meta.className = "history-meta";
    created.textContent = formatDate(row.created_at);
    status.textContent = displayStatus(row.status);
    meta.append(created, status);
    title.textContent = row.goal || "未命名运行";
    copy.textContent = displayModel(row.decision_model) + " · 只读记录";
    button.append(meta, title, copy);
    button.addEventListener("click", () => selectHistory(row).catch(showError));
    item.append(button);
    return item;
  }

  function renderHistoryRows() {
    const list = $("history-list");
    list.replaceChildren();
    $("history-count").textContent = numberFormatter.format(state.historyRows.length) + " 条";

    if (!state.historyRows.length) {
      const item = document.createElement("li");
      item.className = "empty-state";
      const title = document.createElement("strong");
      const copy = document.createElement("span");
      const action = document.createElement("button");
      title.textContent = "还没有保存的运行";
      copy.textContent = "先发起一次 Fake 任务，完成后会在这里出现。";
      action.type = "button";
      action.className = "secondary-button";
      action.textContent = "发起第一个任务";
      action.addEventListener("click", () => route({ name: "new", runId: null }).catch(showError));
      item.append(title, copy, document.createElement("br"), action);
      list.append(item);
      $("history-more").hidden = true;
      return;
    }

    state.historyRows.slice(0, state.historyVisibleCount).forEach((row) => {
      list.append(createHistoryItem(row));
    });

    const remaining = state.historyRows.length - state.historyVisibleCount;
    $("history-more").hidden = remaining <= 0;
    $("history-more").textContent = remaining > 0
      ? "再显示 " + numberFormatter.format(Math.min(HISTORY_BATCH_SIZE, remaining)) + " 条"
      : "已显示全部";
  }

  async function loadHistory() {
    const data = await apiFetch("/api/history");
    state.historyRows = data.runs;
    const selectedIndex = state.historyRows.findIndex((row) => row.run_id === state.selectedHistoryId);
    if (selectedIndex >= state.historyVisibleCount) {
      state.historyVisibleCount = selectedIndex + 1;
    }
    renderHistoryRows();
    if (state.selectedHistoryId) {
      const selected = data.runs.find((row) => row.run_id === state.selectedHistoryId);
      if (selected) await selectHistory(selected);
    }
  }

  function taskProgress(record) {
    const plan = record.events?.find((event) => event.phase === "plan_created")?.output?.tasks || [];
    if (!plan.length) return "—";
    const completed = record.events.filter((event) => event.phase === "task_completed").length;
    return completed + " / " + plan.length;
  }

  function displayModel(model) {
    if (model === "deepseek") return "DeepSeek";
    if (model === "fake") return "Fake";
    return "Unknown";
  }

  async function selectHistory(row) {
    state.selectedHistoryId = row.run_id;
    document.querySelectorAll("[data-history-id]").forEach((button) => {
      const selected = button.dataset.historyId === row.run_id;
      button.classList.toggle("selected", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });
    $("history-detail").setAttribute("aria-busy", "true");
    $("history-title").textContent = row.goal || "未命名运行";
    $("history-description").textContent = "正在加载这份只读概要…";
    $("history-model").textContent = displayModel(row.decision_model);
    $("history-status").textContent = displayStatus(row.status);
    $("history-tasks").textContent = "—";
    $("replay-run").disabled = true;
    const record = await apiFetch("/api/history/" + encodeURIComponent(row.run_id));
    if (state.selectedHistoryId !== row.run_id) return;
    const answer = [...(record.events || [])].reverse().find((event) => event.phase === "final_answer")?.output?.message;
    $("history-description").textContent = answer || "该运行没有最终回答；打开完整过程可查看失败位置。";
    $("history-model").textContent = displayModel(record.decision_model);
    $("history-status").textContent = displayStatus(record.status);
    $("history-tasks").textContent = taskProgress(record);
    $("history-detail").setAttribute("aria-busy", "false");
    $("replay-run").disabled = false;
  }

  async function loadHistoricalRun(runId) {
    const record = await apiFetch("/api/history/" + encodeURIComponent(runId));
    state.selectedHistoryId = runId;
    state.viewingHistoricalRunId = runId;
    renderRun(record, true);
    $("history-title").textContent = record.user_goal;
    $("history-model").textContent = displayModel(record.decision_model);
    $("history-status").textContent = displayStatus(record.status);
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

  document.querySelectorAll("button[data-route]").forEach((button) => {
    button.addEventListener("click", () => route({ name: button.dataset.route, runId: null }).catch(showError));
  });

  $("goal-input").addEventListener("input", () => {
    setFieldError("goal-error");
    clearMessage();
    updateLaunchState();
  });

  document.querySelectorAll("input[name=model]").forEach((input) => {
    input.addEventListener("change", () => {
      setFieldError("key-error");
      clearMessage();
      updateLaunchState();
    });
  });

  document.querySelectorAll("[data-preset-goal]").forEach((button) => {
    button.addEventListener("click", () => {
      $("goal-input").value = button.dataset.presetGoal || "";
      setFieldError("goal-error");
      updateLaunchState();
      $("goal-input").focus();
    });
  });

  $("configure-key").addEventListener("click", async () => {
    const apiKey = $("deepseek-key").value.trim();
    if (!apiKey) {
      setFieldError("key-error", "请输入本次服务使用的 DeepSeek Key。");
      $("deepseek-key").focus();
      return;
    }
    state.keyPending = true;
    setFieldError("key-error");
    clearMessage();
    updateLaunchState();
    try {
      await apiFetch("/api/deepseek-key", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Origin: location.origin },
        body: JSON.stringify({ api_key: apiKey }),
      });
      $("app-message").textContent = "Key 已保存到当前服务进程内存。";
      $("app-message").hidden = false;
      await bootstrap();
    } catch (error) {
      setFieldError("key-error", (error.message || "Key 保存失败") + " 请检查 Key 后重试。");
      $("deepseek-key").focus();
    } finally {
      $("deepseek-key").value = "";
      state.keyPending = false;
      updateLaunchState();
    }
  });

  $("clear-key").addEventListener("click", async () => {
    state.keyPending = true;
    clearMessage();
    updateLaunchState();
    try {
      await apiFetch("/api/deepseek-key", { method: "DELETE", headers: { Origin: location.origin } });
      $("app-message").textContent = "已清除当前服务内存中的 Key。";
      $("app-message").hidden = false;
      await bootstrap();
    } catch (error) {
      showError(error, "请确认当前没有活动的 DeepSeek 运行后重试。");
    } finally {
      state.keyPending = false;
      updateLaunchState();
    }
  });

  $("replay-run").addEventListener("click", () => {
    if (state.selectedHistoryId) {
      route({ name: "trace", runId: state.selectedHistoryId }).catch(showError);
    }
  });

  $("history-more").addEventListener("click", () => {
    state.historyVisibleCount += HISTORY_BATCH_SIZE;
    renderHistoryRows();
  });

  $("start-run").addEventListener("click", async () => {
    const goal = $("goal-input").value.trim();
    if (!goal) {
      setFieldError("goal-error", "请输入任务目标，例如“阅读工作区资料并总结这个 demo”。");
      $("goal-input").focus();
      return;
    }
    state.runPending = true;
    setFieldError("goal-error");
    clearMessage();
    updateLaunchState();
    try {
      const run = await apiFetch("/api/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json", Origin: location.origin },
        body: JSON.stringify({
          goal,
          decision_model: $("model-deepseek").checked ? "deepseek" : "fake",
        }),
      });
      state.currentRun = run;
      state.viewingHistoricalRunId = null;
      renderServiceState();
      connectCurrentRun(run);
      await route({ name: "trace", runId: null });
    } catch (error) {
      setFieldError("goal-error", (error.message || "任务启动失败") + " 请检查服务状态后重试。");
      $("goal-input").focus();
    } finally {
      state.runPending = false;
      updateLaunchState();
    }
  });

  $("pending-permission-button").addEventListener("click", openPermissionDrawer);
  $("permission-backdrop").addEventListener("click", closePermissionDrawer);
  $("close-permission").addEventListener("click", closePermissionDrawer);
  $("approve-permission").addEventListener("click", () => resolvePermission(true).catch(showError));
  $("reject-permission").addEventListener("click", () => resolvePermission(false).catch(showError));

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && $("permission-drawer").getAttribute("aria-hidden") === "false") {
      closePermissionDrawer();
      return;
    }
    trapPermissionFocus(event);
  });

  window.addEventListener("hashchange", () => route().catch(showError));
  window.addEventListener("beforeunload", (event) => {
    if ($("goal-input").value.trim() && !state.currentRun?.active) {
      event.preventDefault();
      event.returnValue = "";
    }
  });

  viewer = window.MinAgentTraceViewer.create({ root: document.querySelector("[data-trace-viewer-root]") });
  bootstrap().catch(showError);
})();
