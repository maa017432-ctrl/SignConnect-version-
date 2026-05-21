(function () {
  "use strict";

  const seedNode = document.getElementById("admin-dashboard-data");
  const usersBody = document.getElementById("admin-users-tbody");
  if (!seedNode || !usersBody) {
    return;
  }

  const state = {
    dashboard: JSON.parse(seedNode.textContent || "{}"),
    charts: [],
    userQuery: "",
    vocabQuery: "",
    userDebounce: null,
    vocabDebounce: null,
  };

  const refs = {
    userSearch: document.getElementById("admin-user-search"),
    runDiagnostics: document.getElementById("admin-run-diagnostics"),
    diagnosticResults: document.getElementById("diagnostic-results"),
    vocabSearch: document.getElementById("admin-vocabulary-search"),
    vocabTbody: document.getElementById("admin-vocabulary-tbody"),

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

  function renderVocabulary(matches, total) {
    if (!refs.vocabTbody) return;
    if (!Array.isArray(matches) || matches.length === 0) {
      refs.vocabTbody.innerHTML = `
        <tr>
          <td colspan="3" class="sc-muted" style="text-align: center; padding: 1.5rem 0;">
            No gesture classes match the query. (Total: ${total})
          </td>
        </tr>`;
      return;
    }

    const fragment = document.createDocumentFragment();
    matches.forEach((item) => {
      const tr = document.createElement("tr");

      const idCell = document.createElement("td");
      idCell.style.padding = "0.5rem 0.75rem";
      idCell.textContent = String(item.index);

      const labelCell = document.createElement("td");
      labelCell.style.padding = "0.5rem 0.75rem";
      const strong = document.createElement("strong");
      strong.textContent = item.label;
      labelCell.appendChild(strong);

      const statusCell = document.createElement("td");
      statusCell.style.padding = "0.5rem 0.75rem";
      const badge = document.createElement("span");
      badge.className = "sc-badge";
      badge.style.fontSize = "0.7rem";
      badge.style.padding = "0.1rem 0.4rem";
      badge.style.background = "rgba(79, 70, 229, 0.1)";
      badge.style.borderColor = "rgba(79, 70, 229, 0.2)";
      badge.style.color = "var(--accent, #4f46e5)";
      badge.textContent = "Trained";
      statusCell.appendChild(badge);

      tr.append(idCell, labelCell, statusCell);
      fragment.appendChild(tr);
    });

    refs.vocabTbody.replaceChildren(fragment);
  }

  async function runSystemDiagnostics() {
    if (!refs.runDiagnostics || !refs.diagnosticResults) return;
    refs.runDiagnostics.disabled = true;
    refs.runDiagnostics.textContent = "Running diagnostics self-test...";
    refs.diagnosticResults.innerHTML = `
      <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 1.5rem 0; gap: 0.5rem;">
        <span class="sc-muted" style="font-size: 0.8125rem;">Executing SignConnect test suite...</span>
      </div>`;

    try {

      const payload = await fetchJson("/api/admin/system/diagnostics");


      const fragment = document.createDocumentFragment();
      payload.checks.forEach((check) => {
        const div = document.createElement("div");
        div.style.display = "flex";
        div.style.alignItems = "center";
        div.style.justifyContent = "space-between";
        div.style.padding = "0.5rem 0.75rem";
        div.style.borderRadius = "0.375rem";
        div.style.background = "rgba(148, 163, 184, 0.06)";
        div.style.border = "1px solid rgba(148, 163, 184, 0.1)";
        div.style.fontSize = "0.8125rem";

        const labelSpan = document.createElement("span");
        labelSpan.textContent = check.name;

        const rightSide = document.createElement("div");
        rightSide.style.display = "flex";
        rightSide.style.alignItems = "center";
        rightSide.style.gap = "0.5rem";

        const metricSpan = document.createElement("span");
        metricSpan.className = "sc-muted";
        metricSpan.style.fontSize = "0.75rem";
        metricSpan.textContent = check.metric;

        const badge = document.createElement("span");
        badge.style.fontSize = "0.7rem";
        badge.style.padding = "0.15rem 0.4rem";
        badge.style.borderRadius = "0.25rem";
        badge.style.fontWeight = "bold";

        if (check.status.startsWith("PASS")) {
          badge.style.background = "rgba(16, 185, 129, 0.12)";
          badge.style.color = "#10b981";
          badge.textContent = "PASS";

        } else if (check.status === "STANDBY") {
          badge.style.background = "rgba(245, 158, 11, 0.12)";
          badge.style.color = "#f59e0b";
          badge.textContent = "STANDBY";

        } else {
          badge.style.background = "rgba(239, 68, 68, 0.12)";
          badge.style.color = "#ef4444";
          badge.textContent = "FAIL";

        }

        rightSide.append(metricSpan, badge);
        div.append(labelSpan, rightSide);
        fragment.appendChild(div);
      });

      refs.diagnosticResults.replaceChildren(fragment);
    } catch (error) {

      refs.diagnosticResults.innerHTML = `
        <div style="color: #ef4444; text-align: center; padding: 1.5rem 0; font-size: 0.8125rem;">
          Error running diagnostic tests: ${error.message}
        </div>`;
    } finally {
      refs.runDiagnostics.disabled = false;
      refs.runDiagnostics.textContent = "Run Diagnostics Suite";
    }
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
      "monitor-last-label": monitoring.last_prediction_label || "—",
      "monitor-last-confidence": `${Number(monitoring.last_prediction_confidence || 0).toFixed(1)}%`,
      "monitor-model-mode": monitoring.demo_mode ? "Demo" : "Live",
      "monitor-last-update": monitoring.last_prediction_at || "Waiting",
    };
    Object.entries(map).forEach(([id, value]) => {
      const node = document.getElementById(id);
      if (node) node.textContent = String(value);
    });
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

  async function refreshVocab() {
    if (!state.vocabQuery) {
      if (refs.vocabTbody) {
        refs.vocabTbody.innerHTML = `
          <tr>
            <td colspan="3" class="sc-muted" style="text-align: center; padding: 1.5rem 0;">
              Type a word to query AI class indices.
            </td>
          </tr>`;
      }
      return;
    }
    const params = new URLSearchParams({ query: state.vocabQuery });
    const payload = await fetchJson(`/api/admin/dictionary/lookup?${params.toString()}`);
    renderVocabulary(payload.matches || [], payload.total_classes || 0);
  }

  async function handleUserAction(button) {
    const action = button.dataset.userAction;
    const userId = button.dataset.userId;
    if (!action || !userId) return;

    if (action === "toggle-suspend") {
      const nextState = button.dataset.userSuspended !== "true";
      const payload = await postForm(`/api/admin/users/${userId}/suspend`, { suspended: nextState ? "true" : "false" });

      await refreshUsers();
      return;
    }

    if (action === "delete") {
      if (!window.confirm("Delete this user?")) return;
      await deleteWithCsrf(`/api/admin/users/${userId}`);

      await Promise.all([refreshUsers(), refreshDashboard()]);
    }
  }

  function debounce(fn, key, wait = 180) {
    clearTimeout(state[key]);
    state[key] = window.setTimeout(fn, wait);
  }

  refs.userSearch?.addEventListener("input", () => {
    state.userQuery = refs.userSearch.value.trim();
    debounce(() => refreshUsers().catch(console.error), "userDebounce");
  });

  refs.vocabSearch?.addEventListener("input", () => {
    state.vocabQuery = refs.vocabSearch.value.trim();
    debounce(() => refreshVocab().catch(console.error), "vocabDebounce");
  });

  refs.runDiagnostics?.addEventListener("click", () => {
    runSystemDiagnostics();
  });



  usersBody.addEventListener("click", (event) => {
    const button = event.target instanceof Element ? event.target.closest("button[data-user-action]") : null;
    if (!(button instanceof HTMLButtonElement)) return;
    handleUserAction(button).catch(console.error);
  });

  window.addEventListener("themeChanged", renderCharts);

  updateSummary(state.dashboard);
  renderCharts();
  renderUsers(state.dashboard.users || []);
  runSystemDiagnostics();

})();
