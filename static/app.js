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
  metricsGroups: document.getElementById("metricsGroups"),
  gantt: document.getElementById("gantt"),
  jqlPreview: document.getElementById("jqlPreview"),
  cacheSource: document.getElementById("cacheSource"),
  lastRefreshAt: document.getElementById("lastRefreshAt"),
  summaryText: document.getElementById("summaryText"),
  summaryIssueKeys: document.getElementById("summaryIssueKeys"),
  sumAssigned: document.getElementById("sumAssigned"),
  sumResolved: document.getElementById("sumResolved"),
  sumUnresolved: document.getElementById("sumUnresolved"),
  sumReopened: document.getElementById("sumReopened"),
  sumNewIssue: document.getElementById("sumNewIssue"),
  sumTransferOut: document.getElementById("sumTransferOut"),
  sumNet: document.getElementById("sumNet"),
  reopenedTableBody: document.querySelector("#reopenedTable tbody"),
  newIssueTableBody: document.querySelector("#newIssueTable tbody"),
  transferOutTableBody: document.querySelector("#transferOutTable tbody"),
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
      node.innerHTML = `<strong>${card.key}</strong><div>${card.summary}</div><small>${card.assignee} | ${card.priority}</small>`;
      node.onclick = () => {
        elements.details.innerHTML = `
          <h3>${card.key}</h3>
          <p>${card.summary}</p>
          <p>状态: ${card.status}</p>
          <p>负责人: ${card.assignee}</p>
          <p>优先级: ${card.priority}</p>
          <p>创建: ${card.timeline.created_at || "-"}</p>
          <p>产品分配: ${card.timeline.product_assigned_at || "-"} ${card.timeline.product_assigned_to ? `(${card.timeline.product_assigned_to})` : ""}</p>
          <p>开发经理分配: ${card.timeline.dev_manager_assigned_at || "-"} ${card.timeline.dev_manager_assigned_from || card.timeline.dev_manager_assigned_to ? `(${card.timeline.dev_manager_assigned_from || "-"} → ${card.timeline.dev_manager_assigned_to || "-"})` : ""}</p>
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
  elements.metricsGroups.innerHTML = "";
  const teamMap = new Map();
  metrics.forEach((row) => {
    const teamName = row.team_name || "其他团队";
    if (!teamMap.has(teamName)) {
      teamMap.set(teamName, []);
    }
    teamMap.get(teamName).push(row);
  });

  const orderedTeamNames = Array.from(teamMap.keys()).sort((left, right) => {
    if (left === "其他团队" && right !== "其他团队") {
      return 1;
    }
    if (left !== "其他团队" && right === "其他团队") {
      return -1;
    }
    return left.localeCompare(right, "zh-CN");
  });

  orderedTeamNames.forEach((teamName) => {
    const rows = teamMap.get(teamName) || [];
    const section = document.createElement("div");
    section.className = "metrics-group";

    const title = document.createElement("h4");
    title.textContent = `团队：${teamName}`;
    section.appendChild(title);

    const table = document.createElement("table");
    table.innerHTML = `
      <thead>
        <tr>
          <th>成员</th>
          <th>总数</th>
          <th>已解决</th>
          <th>已解决Issue</th>
          <th>解决率</th>
          <th>WIP</th>
          <th>平均LeadTime(小时)</th>
          <th>加权进度</th>
        </tr>
      </thead>
      <tbody></tbody>
    `;
    const tbody = table.querySelector("tbody");

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.assignee}</td>
        <td>${row.total}</td>
        <td>${row.resolved}</td>
        <td>${(row.resolved_issue_keys || []).join(", ") || "-"}</td>
        <td>${row.resolution_rate}%</td>
        <td>${row.wip}</td>
        <td>${row.avg_lead_time_hours ?? "-"}</td>
        <td>${row.weighted_progress}%</td>
      `;
      tbody.appendChild(tr);
    });

    const subtotalTotal = rows.reduce((sum, row) => sum + Number(row.total || 0), 0);
    const subtotalResolved = rows.reduce((sum, row) => sum + Number(row.resolved || 0), 0);
    const subtotalWip = rows.reduce((sum, row) => sum + Number(row.wip || 0), 0);
    const resolutionRate = subtotalTotal ? ((subtotalResolved / subtotalTotal) * 100).toFixed(2) : "0.00";

    const leadNumerator = rows.reduce((sum, row) => {
      if (row.avg_lead_time_hours == null) {
        return sum;
      }
      return sum + Number(row.avg_lead_time_hours) * Number(row.total || 0);
    }, 0);
    const leadDenominator = rows.reduce((sum, row) => {
      if (row.avg_lead_time_hours == null) {
        return sum;
      }
      return sum + Number(row.total || 0);
    }, 0);
    const avgLead = leadDenominator ? (leadNumerator / leadDenominator).toFixed(2) : "-";

    const subtotalRow = document.createElement("tr");
    subtotalRow.className = "metrics-subtotal";
    subtotalRow.innerHTML = `
      <td>小计</td>
      <td>${subtotalTotal}</td>
      <td>${subtotalResolved}</td>
      <td>-</td>
      <td>${resolutionRate}%</td>
      <td>${subtotalWip}</td>
      <td>${avgLead}</td>
      <td>-</td>
    `;
    tbody.appendChild(subtotalRow);

    section.appendChild(table);
    elements.metricsGroups.appendChild(section);
  });
}

function renderSummary(kanbanData) {
  const summary = kanbanData.manager_summary_cards || {};
  const issueKeys = kanbanData.manager_summary_issue_keys || {};
  elements.sumAssigned.textContent = summary.assigned_total ?? "-";
  elements.sumResolved.textContent = summary.resolved_total ?? "-";
  elements.sumUnresolved.textContent = summary.unresolved_total ?? "-";
  elements.sumReopened.textContent = summary.reopened_event_total ?? "-";
  elements.sumNewIssue.textContent = summary.new_issue_total ?? "-";
  const transferIssue = summary.transfer_out_issue_total ?? 0;
  const transferEvent = summary.transfer_out_event_total ?? 0;
  elements.sumTransferOut.textContent = `${transferIssue}个问题 / ${transferEvent}次`;
  elements.sumNet.textContent = summary.net_change ?? "-";
  elements.summaryText.value = kanbanData.manager_summary_text || "";

  const formatIssueLine = (label, keys) => `${label}: ${(keys || []).join(", ") || "-"}`;
  elements.summaryIssueKeys.textContent = [
    "问题号明细",
    formatIssueLine("本周期分配", issueKeys.assigned),
    formatIssueLine("本周期已解决", issueKeys.resolved),
    formatIssueLine("本周期未解决", issueKeys.unresolved),
    formatIssueLine("重开事件", issueKeys.reopened),
    formatIssueLine("New Issue", issueKeys.new_issue),
    formatIssueLine("评估后转出", issueKeys.transfer_out),
  ].join("\n");
}

function renderFocus(kanbanData) {
  const focus = kanbanData.period_focus || {};
  const reopenedItems = focus.reopened?.items || [];
  const newIssueItems = focus.new_issue?.items || [];
  const transferTeams = focus.transfer_out?.teams || [];

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

  elements.transferOutTableBody.innerHTML = "";
  transferTeams.forEach((team) => {
    const teamName = team.team_name || team.team_id || "-";
    const transferItems = team.items || [];
    transferItems.forEach((item) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><a href="${item.url || "#"}" target="_blank">${item.key || "-"}</a></td>
        <td>${teamName}</td>
        <td>${item.from || "-"} → ${item.to || "-"}</td>
        <td>${item.event_count ?? 0}</td>
        <td>${item.latest_transfer_out_at || "-"}</td>
      `;
      elements.transferOutTableBody.appendChild(tr);
    });
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
