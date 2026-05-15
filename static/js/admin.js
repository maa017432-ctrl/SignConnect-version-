(function () {
  "use strict";

  const seedNode = document.getElementById("admin-dashboard-data");
  const usersBody = document.getElementById("admin-users-tbody");
  const translationsBody = document.getElementById("admin-translations-tbody");
  if (!seedNode || !usersBody || !translationsBody) {
    return;
  }

  const state = {
    dashboard: JSON.parse(seedNode.textContent || "{}"),
    charts: [],
    userQuery: "",
    translationQuery: "",
    userDebounce: null,
    translationDebounce: null,
  };

  const refs = {
    userSearch: document.getElementById("admin-user-search"),
    translationSearch: document.getElementById("admin-translation-search"),
    exportBtn: document.getElementById("admin-export-btn"),
    thresholdInput: document.getElementById("admin-threshold-input"),
    thresholdValue: document.getElementById("admin-threshold-value"),
    cameraInput: document.getElementById("admin-camera-input"),
    feedback: document.getElementById("admin-system-feedback"),
    connectedUsers: document.getElementById("admin-connected-users"),
    avgConfidence: document.getElementById("admin-avg-confidence"),
  };

  function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
  }

  function escHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setFeedback(message, type = "info") {
    if (!refs.feedback) return;
    refs.feedback.textContent = message;
    refs.feedback.dataset.state = type;
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, { cache: "no-store", ...options });
    let payload = {};
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) {
      throw new Error(payload.error || `Request failed (${response.status})`);
    }
    return payload;
  }

  async function postForm(url, body) {
    return fetchJson(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
      body: new URLSearchParams({ ...body, csrf_token: getCsrfToken() }).toString(),
    });
  }

  async function deleteWithCsrf(url) {
    return fetchJson(url, {
      method: "DELETE",
      headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
      body: new URLSearchParams({ csrf_token: getCsrfToken() }).toString(),
    });
  }

  function formatConfidence(value) {
    return `${Number(value || 0).toFixed(1)}%`;
  }

  function statusClass(status) {
    return `sc-admin-status sc-admin-status--${String(status || "inactive").toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
  }

  function clearTable(body, colspan, message) {
    body.replaceChildren();
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = colspan;
    cell.className = "sc-empty-state";
    const paragraph = document.createElement("p");
    paragraph.textContent = message;
    cell.appendChild(paragraph);
    row.appendChild(cell);
    body.appendChild(row);
  }

  function renderUsers(users) {
    if (!Array.isArray(users) || users.length === 0) {
      clearTable(usersBody, 6, "No users matched the current search.");
      return;
    }

    const fragment = document.createDocumentFragment();
    users.forEach((user) => {
      const row = document.createElement("tr");

      const userCell = document.createElement("td");
      const name = document.createElement("strong");
      name.textContent = user.full_name;
      const email = document.createElement("span");
      email.className = "sc-muted";
      email.textContent = user.email;
      userCell.append(name, document.createElement("br"), email);

      const statusCell = document.createElement("td");
      const status = document.createElement("span");
      status.className = statusClass(user.activity_status);
      status.textContent = user.activity_status;
      statusCell.appendChild(status);

      const translationsCell = document.createElement("td");
      translationsCell.textContent = String(user.translations);

      const confidenceCell = document.createElement("td");
      confidenceCell.textContent = formatConfidence(user.avg_confidence);

      const activityCell = document.createElement("td");
      activityCell.textContent = user.last_active || "No activity yet";

      const actionsCell = document.createElement("td");
      const actions = document.createElement("div");
      actions.className = "sc-admin-inline-actions";

      const suspendButton = document.createElement("button");
      suspendButton.type = "button";
      suspendButton.className = "sc-btn sc-btn--sm";
      suspendButton.dataset.userAction = "toggle-suspend";
      suspendButton.dataset.userId = String(user.id);
      suspendButton.dataset.userSuspended = user.is_suspended ? "true" : "false";
      suspendButton.textContent = user.is_suspended ? "Reactivate" : "Suspend";

      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "sc-btn sc-btn--sm sc-btn--danger";
      deleteButton.dataset.userAction = "delete";
      deleteButton.dataset.userId = String(user.id);
      deleteButton.textContent = "Delete";

      actions.append(suspendButton, deleteButton);
      actionsCell.appendChild(actions);
      row.append(userCell, statusCell, translationsCell, confidenceCell, activityCell, actionsCell);
      fragment.appendChild(row);
    });

    usersBody.replaceChildren(fragment);
  }

  function renderTranslations(rows) {
    if (!Array.isArray(rows) || rows.length === 0) {
      clearTable(translationsBody, 5, "No translation records matched the current filters.");
      return;
    }

    const fragment = document.createDocumentFragment();
    rows.forEach((row) => {
      const tr = document.createElement("tr");

      const gestureCell = document.createElement("td");
      const tag = document.createElement("span");
      tag.className = "sc-gesture-tag";
      tag.textContent = row.gesture_label;
      gestureCell.appendChild(tag);

      const confidenceCell = document.createElement("td");
      confidenceCell.textContent = `${Number(row.confidence_pct || 0).toFixed(2)}%`;

      const userCell = document.createElement("td");
      const name = document.createElement("strong");
      name.textContent = row.user_name;
      const email = document.createElement("span");
      email.className = "sc-muted";
      email.textContent = row.user_email;
      userCell.append(name, document.createElement("br"), email);

      const createdCell = document.createElement("td");
      createdCell.textContent = row.created_at || "—";

      const audioCell = document.createElement("td");
      if (row.audio_path) {
        const audio = document.createElement("audio");
        audio.className = "sc-audio";
        audio.controls = true;
        audio.preload = "none";
        audio.src = row.audio_path;
        audioCell.appendChild(audio);
      } else {
        audioCell.textContent = "—";
      }

      tr.append(gestureCell, confidenceCell, userCell, createdCell, audioCell);
      fragment.appendChild(tr);
    });

    translationsBody.replaceChildren(fragment);
  }

  function updateSummary(payload) {
    state.dashboard = payload;
    const stats = payload.stats || {};
    const monitoring = payload.monitoring || {};
    const map = {
      "stat-total-translations": stats.total_translations,
      "stat-total-users": stats.total_users,
      "stat-active-sessions": stats.active_sessions,
      "stat-average-confidence": `${Number(stats.average_confidence || 0).toFixed(1)}%`,
      "stat-predictions-served": stats.predictions_served,
      "stat-avg-latency": `${Number(stats.avg_inference_ms || 0).toFixed(1)} ms`,
      "monitor-connected-users": monitoring.connected_users,
      "monitor-active-sessions": monitoring.active_sessions,
      "monitor-last-label": monitoring.last_prediction_label || "—",
      "monitor-last-confidence": `${Number(monitoring.last_prediction_confidence || 0).toFixed(1)}%`,
      "monitor-model-mode": monitoring.demo_mode ? "Demo" : "Live",
      "monitor-last-update": monitoring.last_prediction_at || "Waiting",
    };
    Object.entries(map).forEach(([id, value]) => {
      const node = document.getElementById(id);
      if (node) node.textContent = String(value);
    });
    if (refs.connectedUsers) refs.connectedUsers.textContent = String(monitoring.connected_users || 0);
    if (refs.avgConfidence) refs.avgConfidence.textContent = `${Number(stats.average_confidence || 0).toFixed(1)}%`;
    if (refs.thresholdInput) refs.thresholdInput.value = Math.round(Number(payload.settings?.confidence_threshold || 75));
    if (refs.thresholdValue) refs.thresholdValue.textContent = `${Math.round(Number(payload.settings?.confidence_threshold || 75))}%`;
    if (refs.cameraInput) refs.cameraInput.value = String(payload.settings?.camera_index ?? 0);
  }

  function chartTheme() {
    const light = document.documentElement.getAttribute("data-theme") === "light";
    return light ? {
      grid: "rgba(15, 23, 42, 0.10)",
      tick: "#334155",
      tooltipBg: "rgba(255,255,255,0.98)",
      tooltipTitle: "#0f172a",
      tooltipBody: "#334155",
      doughnutBorder: "rgba(255,255,255,0.92)",
      lineFill: "rgba(139,92,246,0.14)",
      barFill: "rgba(59,130,246,0.65)",
      barStroke: "#3b82f6",
    } : {
      grid: "rgba(148, 163, 184, 0.18)",
      tick: "#cbd5e1",
      tooltipBg: "rgba(15,23,42,0.95)",
      tooltipTitle: "#f8fafc",
      tooltipBody: "#cbd5e1",
      doughnutBorder: "rgba(15,23,42,0.92)",
      lineFill: "rgba(139,92,246,0.24)",
      barFill: "rgba(59,130,246,0.78)",
      barStroke: "#60a5fa",
    };
  }

  function destroyCharts() {
    state.charts.forEach((chart) => chart.destroy());
    state.charts = [];
  }

  function renderCharts() {
    if (typeof Chart === "undefined") return;
    destroyCharts();
    const theme = chartTheme();
    const chartData = state.dashboard.charts || {};
    const baseOptions = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: theme.tick, boxWidth: 12, usePointStyle: true } },
        tooltip: {
          backgroundColor: theme.tooltipBg,
          titleColor: theme.tooltipTitle,
          bodyColor: theme.tooltipBody,
        },
      },
      scales: {
        x: { ticks: { color: theme.tick }, grid: { color: theme.grid } },
        y: { ticks: { color: theme.tick }, grid: { color: theme.grid }, beginAtZero: true },
      },
    };

    state.charts.push(new Chart(document.getElementById("translationsChart"), {
      type: "line",
      data: {
        labels: chartData.translations_over_time?.labels || [],
        datasets: [{
          label: "Translations",
          data: chartData.translations_over_time?.values || [],
          borderColor: "#8b5cf6",
          backgroundColor: theme.lineFill,
          fill: true,
          tension: 0.35,
          pointRadius: 4,
        }],
      },
      options: baseOptions,
    }));

    state.charts.push(new Chart(document.getElementById("gesturesChart"), {
      type: "doughnut",
      data: {
        labels: chartData.top_gestures?.labels || [],
        datasets: [{
          data: chartData.top_gestures?.values || [],
          backgroundColor: ["#8b5cf6", "#3b82f6", "#06b6d4", "#10b981", "#f59e0b", "#ef4444"],
          borderColor: theme.doughnutBorder,
          borderWidth: 3,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: baseOptions.plugins,
      },
    }));

    state.charts.push(new Chart(document.getElementById("confidenceChart"), {
      type: "bar",
      data: {
        labels: chartData.confidence_by_gesture?.labels || [],
        datasets: [{
          label: "Average confidence (%)",
          data: chartData.confidence_by_gesture?.values || [],
          backgroundColor: theme.barFill,
          borderColor: theme.barStroke,
          borderWidth: 1.5,
          borderRadius: 10,
        }],
      },
      options: {
        ...baseOptions,
        indexAxis: "y",
        scales: {
          x: { ticks: { color: theme.tick }, grid: { color: theme.grid }, beginAtZero: true, max: 100 },
          y: { ticks: { color: theme.tick }, grid: { display: false } },
        },
      },
    }));
  }

  async function refreshDashboard() {
    const payload = await fetchJson("/api/admin/dashboard");
    updateSummary(payload);
    renderCharts();
  }

  async function refreshUsers() {
    const params = new URLSearchParams({ query: state.userQuery, limit: "50" });
    const payload = await fetchJson(`/api/admin/users?${params.toString()}`);
    renderUsers(payload.users || []);
  }

  async function refreshTranslations() {
    const params = new URLSearchParams({ query: state.translationQuery, limit: "100" });
    const payload = await fetchJson(`/api/admin/translations?${params.toString()}`);
    renderTranslations(payload.translations || []);
  }

  async function handleUserAction(button) {
    const action = button.dataset.userAction;
    const userId = button.dataset.userId;
    if (!action || !userId) return;

    if (action === "toggle-suspend") {
      const nextState = button.dataset.userSuspended !== "true";
      const payload = await postForm(`/api/admin/users/${userId}/suspend`, { suspended: nextState ? "true" : "false" });
      setFeedback(payload.is_suspended ? "User suspended successfully." : "User reactivated successfully.", "success");
      await refreshUsers();
      return;
    }

    if (action === "delete") {
      if (!window.confirm("Delete this user and all linked translations?")) return;
      await deleteWithCsrf(`/api/admin/users/${userId}`);
      setFeedback("User deleted successfully.", "success");
      await Promise.all([refreshUsers(), refreshTranslations(), refreshDashboard()]);
    }
  }

  async function handleAdminAction(action) {
    if (!action) return;
    if (action === "save-settings") {
      const threshold = Number(refs.thresholdInput?.value || 75) / 100;
      const cameraIndex = Number(refs.cameraInput?.value || 0);
      await Promise.all([
        postForm("/api/admin/system/config", { confidence_threshold: String(threshold) }),
        postForm("/api/camera", { camera_index: String(cameraIndex) }),
      ]);
      setFeedback("Runtime settings saved.", "success");
      await refreshDashboard();
      return;
    }

    if (action === "reload-model") {
      await postForm("/api/admin/system/reload-model", {});
      setFeedback("AI model reload requested.", "success");
      await refreshDashboard();
      return;
    }

    if (action === "clear-history") {
      if (!window.confirm("Clear all translation history? This cannot be undone.")) return;
      const payload = await postForm("/api/admin/system/clear-history", {});
      setFeedback(`Cleared ${payload.deleted || 0} translation rows.`, "success");
      await Promise.all([refreshDashboard(), refreshTranslations()]);
      return;
    }

    if (action === "clear-logs") {
      const payload = await postForm("/api/admin/system/clear-logs", {});
      setFeedback(payload.message || "Log file cleared.", "success");
    }
  }

  function debounce(fn, key, wait = 180) {
    clearTimeout(state[key]);
    state[key] = window.setTimeout(fn, wait);
  }

  refs.userSearch?.addEventListener("input", () => {
    state.userQuery = refs.userSearch.value.trim();
    debounce(() => refreshUsers().catch((error) => setFeedback(error.message, "error")), "userDebounce");
  });

  refs.translationSearch?.addEventListener("input", () => {
    state.translationQuery = refs.translationSearch.value.trim();
    debounce(() => refreshTranslations().catch((error) => setFeedback(error.message, "error")), "translationDebounce");
  });

  refs.thresholdInput?.addEventListener("input", () => {
    if (refs.thresholdValue) refs.thresholdValue.textContent = `${refs.thresholdInput.value}%`;
  });

  usersBody.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("button[data-user-action]") : null;
    if (!(button instanceof HTMLButtonElement)) return;
    handleUserAction(button).catch((error) => setFeedback(error.message, "error"));
  });

  document.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("button[data-admin-action]") : null;
    if (!(button instanceof HTMLButtonElement)) return;
    handleAdminAction(button.dataset.adminAction).catch((error) => setFeedback(error.message, "error"));
  });

  refs.exportBtn?.addEventListener("click", () => {
    const params = new URLSearchParams({ query: state.translationQuery, limit: "200" });
    window.location.href = `/api/admin/translations/export?${params.toString()}`;
  });

  window.addEventListener("themeChanged", renderCharts);

  updateSummary(state.dashboard);
  renderCharts();
  renderUsers(state.dashboard.users || []);
  renderTranslations(state.dashboard.translations || []);
})();
