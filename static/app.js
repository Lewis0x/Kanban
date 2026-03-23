const elements = {
  assigneeSelect: document.getElementById("assigneeSelect"),
  prioritySelect: document.getElementById("prioritySelect"),
  keywordInput: document.getElementById("keywordInput"),
  modeSelect: document.getElementById("modeSelect"),
  sourceModeSelect: document.getElementById("sourceModeSelect"),
  cacheIdSelect: document.getElementById("cacheIdSelect"),
  windowSelect: document.getElementById("windowSelect"),
  periodStartInput: document.getElementById("periodStartInput"),
  periodEndInput: document.getElementById("periodEndInput"),
  customDateRange: document.getElementById("customDateRange"),
  toggleAdvancedFilters: document.getElementById("toggleAdvancedFilters"),
  advancedFilters: document.getElementById("advancedFilters"),
  toggleAnalysisBtn: document.getElementById("toggleAnalysisBtn"),
  analysisBody: document.getElementById("analysisBody"),
  jqlInput: document.getElementById("jqlInput"),
  syncJiraBtn: document.getElementById("syncJiraBtn"),
  refreshBtn: document.getElementById("refreshBtn"),
  copySummaryBtn: document.getElementById("copySummaryBtn"),
  kanban: document.getElementById("kanban"),
  details: document.getElementById("details"),
  metricsBody: document.querySelector("#metricsTable tbody"),
  gantt: document.getElementById("gantt"),
  jqlPreview: document.getElementById("jqlPreview"),
  cacheSource: document.getElementById("cacheSource"),
  lastRefreshAt: document.getElementById("lastRefreshAt"),
  summaryText: document.getElementById("summaryText"),
  sumAssigned: document.getElementById("sumAssigned"),
  sumResolved: document.getElementById("sumResolved"),
  sumUnresolved: document.getElementById("sumUnresolved"),
  sumReopened: document.getElementById("sumReopened"),
  sumNewIssue: document.getElementById("sumNewIssue"),
  sumNet: document.getElementById("sumNet"),
  reopenedTableBody: document.querySelector("#reopenedTable tbody"),
  newIssueTableBody: document.querySelector("#newIssueTable tbody"),
  csvExport: document.getElementById("csvExport"),
  xlsxExport: document.getElementById("xlsxExport"),
  pngExport: document.getElementById("pngExport"),
};

const CACHE_ROOT = "storage/jira_query_cache";

const state = {
  cacheSources: [],
};

function buildQuery() {
  const params = new URLSearchParams();
  if (elements.sourceModeSelect.value) params.set("source", elements.sourceModeSelect.value);
  if (elements.sourceModeSelect.value === "cache_id" && elements.cacheIdSelect.value) {
    params.set("cache_id", elements.cacheIdSelect.value);
  }
  if (elements.windowSelect.value) params.set("window", elements.windowSelect.value);
  if (elements.periodStartInput.value) params.set("start", `${elements.periodStartInput.value}T00:00:00+08:00`);
  if (elements.periodEndInput.value) params.set("end", `${elements.periodEndInput.value}T23:59:59+08:00`);
  if (elements.assigneeSelect.value) params.set("assignee", elements.assigneeSelect.value);
  if (elements.prioritySelect.value) params.set("priority", elements.prioritySelect.value);
  if (elements.keywordInput.value) params.set("q", elements.keywordInput.value);
  if (elements.jqlInput.value) params.set("jql", elements.jqlInput.value);
  return params;
}

const apiClient = {
  async getCachedQueries() {
    const response = await fetch("/api/cached_queries");
    return response.json();
  },
  async getCacheSources() {
    const response = await fetch("/api/cache_sources");
    return response.json();
  },
  async runQuery(query) {
    const queryUrl = query ? `/api/query?${query}&confirmed=true` : "/api/query?confirmed=true";
    return fetch(queryUrl, { method: "POST" });
  },
  async getKanban(query) {
    return fetch(`/api/kanban?${query}`);
  },
  async getGantt(query, mode) {
    return fetch(`/api/gantt?${query}&mode=${encodeURIComponent(mode)}`);
  },
};

function setExportLinks() {
  const query = buildQuery().toString();
  elements.csvExport.href = `/api/export/csv?${query}`;
  elements.xlsxExport.href = `/api/export/xlsx?${query}`;
  elements.pngExport.href = `/api/export/png?${query}&mode=${encodeURIComponent(elements.modeSelect.value)}`;
}

function renderCards(columns, cards) {
  elements.kanban.innerHTML = "";
  ["To Do", "In Progress", "审核中", "Done"].forEach((name) => {
    const col = document.createElement("div");
    col.className = "column";
    col.innerHTML = `<h3>${name} (${(columns[name] || []).length})</h3>`;
    (columns[name] || []).forEach((card) => {
      const node = document.createElement("div");
      node.className = "card";
      const owner = card.metric_owner || card.assignee;
      node.innerHTML = `<strong>${card.key}</strong><div>${card.summary}</div><small>${owner} | ${card.priority}</small>`;
      node.onclick = () => {
        elements.details.innerHTML = `
          <h3>${card.key}</h3>
          <p>${card.summary}</p>
          <p>状态: ${card.status}</p>
          <p>任务负责人: ${card.metric_owner || card.assignee}</p>
          <p>Jira 经办人: ${card.assignee}</p>
          <p>优先级: ${card.priority}</p>
          <p>创建: ${card.timeline.created_at || "-"}</p>
          <p>产品分配: ${card.timeline.product_assigned_at || "-"} ${card.timeline.product_assigned_to ? `(${card.timeline.product_assigned_to})` : ""}</p>
          <p>开发经理分配: ${card.timeline.dev_manager_assigned_at || "-"} ${card.timeline.dev_manager_assigned_to ? `(${card.timeline.dev_manager_assigned_to})` : ""}</p>
          <p>开发开始: ${card.timeline.developer_started_at || "-"}</p>
          <p>审核开始: ${card.timeline.review_at || "-"}</p>
          <p>解决: ${card.timeline.resolved_at || "-"}</p>
          <p><a href="${card.url}" target="_blank">打开JIRA</a></p>
        `;
      };
      col.appendChild(node);
    });
    elements.kanban.appendChild(col);
  });
}

function renderMetrics(metrics) {
  elements.metricsBody.innerHTML = "";
  metrics.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.assignee}</td>
      <td>${row.total}</td>
      <td>${row.resolved}</td>
      <td>${row.resolution_rate}%</td>
      <td>${row.wip}</td>
      <td>${row.avg_lead_time_hours ?? "-"}</td>
      <td>${row.weighted_progress}%</td>
    `;
    elements.metricsBody.appendChild(tr);
  });
}

function renderSummary(kanbanData) {
  const summary = kanbanData.manager_summary_cards || {};
  elements.sumAssigned.textContent = summary.assigned_total ?? "-";
  elements.sumResolved.textContent = summary.resolved_total ?? "-";
  elements.sumUnresolved.textContent = summary.unresolved_total ?? "-";
  elements.sumReopened.textContent = summary.reopened_event_total ?? "-";
  elements.sumNewIssue.textContent = summary.new_issue_total ?? "-";
  elements.sumNet.textContent = summary.net_change ?? "-";
  elements.summaryText.value = kanbanData.manager_summary_text || "";
  // auto-resize textarea to fit content
  elements.summaryText.style.height = "auto";
  elements.summaryText.style.height = elements.summaryText.scrollHeight + "px";
}

function renderFocus(kanbanData) {
  const focus = kanbanData.period_focus || {};
  const reopenedItems = focus.reopened?.items || [];
  const newIssueItems = focus.new_issue?.items || [];

  elements.reopenedTableBody.innerHTML = "";
  reopenedItems.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><a href="${item.url || "#"}" target="_blank">${item.key || "-"}</a></td>
      <td>${item.reopen_count ?? 0}</td>
      <td>${item.metric_owner || item.assignee || "-"}</td>
      <td>${item.last_reopened_at || "-"}</td>
    `;
    elements.reopenedTableBody.appendChild(tr);
  });

  elements.newIssueTableBody.innerHTML = "";
  newIssueItems.forEach((item) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><a href="${item.url || "#"}" target="_blank">${item.key || "-"}</a></td>
      <td>${item.metric_owner || item.assignee || "-"}</td>
      <td>${item.created_at || "-"}</td>
      <td>${item.status || "-"}</td>
    `;
    elements.newIssueTableBody.appendChild(tr);
  });
}

function renderGantt(rows) {
  elements.gantt.innerHTML = "";
  const grouped = {};
  rows.forEach((row) => {
    grouped[row.lane] = grouped[row.lane] || [];
    grouped[row.lane].push(row);
  });

  Object.keys(grouped).forEach((lane) => {
    const laneNode = document.createElement("div");
    laneNode.className = "lane";
    laneNode.innerHTML = `<strong>${lane}</strong>`;
    grouped[lane].forEach((item) => {
      const start = new Date(item.start).getTime();
      const end = new Date(item.end).getTime();
      const durationHours = Math.max((end - start) / 3600000, 1);
      const bar = document.createElement("div");
      bar.className = "bar";
      bar.style.width = `${Math.min(durationHours, 240)}px`;
      bar.title = `${item.key} ${item.summary}`;
      laneNode.appendChild(bar);
    });
    elements.gantt.appendChild(laneNode);
  });
}

async function hydrateCachedQueries(preserveInput = true) {
  const data = await apiClient.getCachedQueries();
  const queries = data.queries || [];
  if ((!preserveInput || !elements.jqlInput.value) && queries.length > 0) {
    elements.jqlInput.value = queries[0].custom_jql || "";
  }
  if ((!preserveInput || !elements.jqlInput.value) && data.default_jql) {
    elements.jqlInput.value = data.default_jql;
  }
}

async function hydrateCacheSources() {
  const data = await apiClient.getCacheSources();
  state.cacheSources = data.sources || [];

  const previous = elements.cacheIdSelect.value;
  elements.cacheIdSelect.innerHTML = '<option value="">选择缓存文件</option>';
  state.cacheSources.forEach((entry) => {
    const option = document.createElement("option");
    option.value = entry.id;
    option.textContent = `${entry.id.slice(0, 12)}... (${entry.issue_count ?? 0}条) ${entry.jql_preview || "(无JQL预览)"}`;
    elements.cacheIdSelect.appendChild(option);
  });

  if (previous && state.cacheSources.some((entry) => entry.id === previous)) {
    elements.cacheIdSelect.value = previous;
  } else if (!elements.cacheIdSelect.value && state.cacheSources.length > 0) {
    elements.cacheIdSelect.value = state.cacheSources[0].id;
  }
}

function updateSourceControls() {
  elements.cacheIdSelect.disabled = elements.sourceModeSelect.value !== "cache_id";
}

function updatePeriodControls() {
  const isCustom = elements.windowSelect.value === "custom";
  if (isCustom) {
    elements.customDateRange.classList.remove("collapsed");
  } else {
    elements.customDateRange.classList.add("collapsed");
  }
}

function toggleAdvancedFilters() {
  const collapsed = elements.advancedFilters.classList.toggle("collapsed");
  elements.toggleAdvancedFilters.textContent = collapsed ? "高级筛选" : "收起高级筛选";
}

function toggleAnalysisPanel() {
  const collapsed = elements.analysisBody.classList.toggle("collapsed");
  elements.toggleAnalysisBtn.textContent = collapsed ? "展开分析区" : "收起分析区";
}

function updateRefreshTime() {
  const now = new Date();
  const formatted = now.toLocaleString("zh-CN", { hour12: false });
  elements.lastRefreshAt.textContent = `最近刷新：${formatted}`;
}

async function refresh() {
  await hydrateCachedQueries(true);
  const query = buildQuery().toString();

  let kanbanRes = await apiClient.getKanban(query);
  if (kanbanRes.status === 409) {
    const confirmed = window.confirm("本地缓存不存在或已失效，是否连接 JIRA 拉取最新数据？");
    if (!confirmed) {
      elements.jqlPreview.textContent = "已取消连接 JIRA。请使用本地缓存或稍后重试。";
      elements.cacheSource.textContent = `缓存来源：${CACHE_ROOT}（未命中）`;
      return;
    }

    const queryRes = await apiClient.runQuery(query);
    if (!queryRes.ok) {
      const queryErr = await queryRes.json();
      elements.jqlPreview.textContent = queryErr.error || "JQL查询失败";
      elements.cacheSource.textContent = `缓存来源：${CACHE_ROOT}（查询失败）`;
      return;
    }

    kanbanRes = await apiClient.getKanban(query);
  }

  if (!kanbanRes.ok) {
    const kanbanErr = await kanbanRes.json();
    elements.jqlPreview.textContent = kanbanErr.error || "看板构建失败";
    elements.cacheSource.textContent = `缓存来源：${CACHE_ROOT}（未命中）`;
    return;
  }

  const kanbanData = await kanbanRes.json();
  renderCards(kanbanData.columns || {}, kanbanData.cards || []);
  renderMetrics(kanbanData.metrics || []);
  renderSummary(kanbanData);
  renderFocus(kanbanData);
  updateRefreshTime();

  elements.jqlPreview.textContent = kanbanData.jql_preview || "-";
  const source = kanbanData.cache_source || CACHE_ROOT;
  const suffix = kanbanData.cache_fallback ? "（离线回退）" : "";
  elements.cacheSource.textContent = `缓存来源：${source}${suffix}`;

  const assignees = kanbanData.filters?.assignees || [];
  const priorities = kanbanData.filters?.priorities || [];

  elements.assigneeSelect.innerHTML = '<option value="">全部负责人</option>';
  assignees.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    elements.assigneeSelect.appendChild(option);
  });

  elements.prioritySelect.innerHTML = '<option value="">全部优先级</option>';
  priorities.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    elements.prioritySelect.appendChild(option);
  });

  const ganttRes = await apiClient.getGantt(query, elements.modeSelect.value);
  if (!ganttRes.ok) {
    const ganttErr = await ganttRes.json();
    elements.jqlPreview.textContent = ganttErr.error || "甘特构建失败";
    elements.cacheSource.textContent = `缓存来源：${CACHE_ROOT}（未命中）`;
    return;
  }

  const ganttData = await ganttRes.json();
  renderGantt(ganttData.rows || []);
  setExportLinks();
}

async function syncFromJiraAndCache() {
  if (!elements.syncJiraBtn) {
    return;
  }

  const query = buildQuery().toString();
  const previousLabel = elements.syncJiraBtn.textContent;
  elements.syncJiraBtn.disabled = true;
  elements.syncJiraBtn.textContent = "更新中...";

  try {
    const queryRes = await apiClient.runQuery(query);
    if (!queryRes.ok) {
      const queryErr = await queryRes.json();
      elements.jqlPreview.textContent = queryErr.error || "从JIRA更新失败";
      return;
    }

    await hydrateCacheSources();
    await refresh();
  } finally {
    elements.syncJiraBtn.disabled = false;
    elements.syncJiraBtn.textContent = previousLabel;
  }
}

elements.modeSelect.addEventListener("change", refresh);
elements.windowSelect.addEventListener("change", () => {
  updatePeriodControls();
  refresh();
});
elements.periodStartInput.addEventListener("change", refresh);
elements.periodEndInput.addEventListener("change", refresh);
elements.toggleAdvancedFilters.addEventListener("click", toggleAdvancedFilters);
elements.toggleAnalysisBtn.addEventListener("click", toggleAnalysisPanel);
elements.sourceModeSelect.addEventListener("change", () => {
  updateSourceControls();
  refresh();
});
elements.cacheIdSelect.addEventListener("change", refresh);
if (elements.syncJiraBtn) {
  elements.syncJiraBtn.addEventListener("click", syncFromJiraAndCache);
}
elements.refreshBtn.addEventListener("click", refresh);
elements.copySummaryBtn.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(elements.summaryText.value || "");
    elements.copySummaryBtn.textContent = "已复制";
    setTimeout(() => {
      elements.copySummaryBtn.textContent = "复制总结";
    }, 1200);
  } catch {
    elements.copySummaryBtn.textContent = "复制失败";
    setTimeout(() => {
      elements.copySummaryBtn.textContent = "复制总结";
    }, 1200);
  }
});

window.addEventListener("load", async () => {
  await hydrateCacheSources();
  await hydrateCachedQueries(false);
  updateSourceControls();
  updatePeriodControls();
  await refresh();
});
