# 开发文档 — Jira Sprint Kanban

## 0. 最新迭代

### 2026-03-09

**周期总结与时间解析**

- 修复「周期总结全部为 0」：JIRA 时间戳 `+0800`（无冒号）导致 `datetime.fromisoformat` 失败 → `app/normalize.py::parse_datetime` 预处理后解析。
- 周期口径：`本周期分配` 按 `dev_manager_assigned_at` 窗口；`本周期未解决` 为周期内被开发经理分配且当前未解决；`本周期解决` 按**最后一次**进入 done 的时间。
- `resolved_at`：由「首次 done」改为「最后一次 done」，当前在 done 且历史缺失时仍可用 `resolutiondate` / 状态回退。

**任务负责人（Task Owner）**

- `normalize_issue`：`fields` 中配置的 `task_owner_field`（`customfield_*`）优先；否则从 changelog 按时间重放最后一次 **Task Owner** 或 **任务负责人**（中文显示名）变更；有值则 `metric_owner = task_owner`。
- `task_owner_field` 配置仅支持 **REST 字段 id**（`customfield_12345` 或纯数字）；已移除 `cf[...]` 写法解析。
- 同步时仅在配置了 `task_owner_field` 时将其加入 search 的 `fields`；不额外请求 `/field`；刷新看板只读缓存。

**测试**

- 新增 / 更新：`parse_datetime`、`resolved_at` 多次解决、Task Owner changelog（含中文字段名）等用例；移除已无对应实现的 `tests/test_jira_client.py`。
- 本地全量回归：**52 passed**。

### 2026-02-25

- 单页分区 UI：状态栏、筛选基础+高级、Kanban/详情 70/30、分析区默认折叠。
- 新增 `app/analytics.py`、`app/period.py`；`/api/kanban` 增量：`summary_window`、`manager_summary_*`、`period_focus` 等。
- 前端：`apiClient` + 状态 + 渲染；周期选择、风险聚焦双表。
- 测试：`tests/test_analytics.py` 等；当时全量 **31 passed**。

## 1. 当前目标与范围

- 只读看板系统，基于 JQL + 本地缓存展示问题进展，不直接写回 JIRA。
- 核心视图：看板、成员指标、甘特图、导出（CSV/Excel/PNG）。
- 当前重点是「准确反映问题解决责任人及开发周期」。

## 2. 架构总览

- 后端：Flask（`app/main.py`）
- 数据获取：JIRA REST API `/rest/api/2/search`（`app/jira_client.py`）
- 本地缓存：`storage/jira_query_cache/*.json`（默认不入库，见 `.gitignore`）
- 领域规则：`app/normalize.py`（状态映射、时间节点、责任人）
- 统计与甘特：`app/metrics.py`
- 前端：`templates/index.html` + `static/app.js`

## 3. 配置说明（config/jira_auth.yaml）

必填：`base_url`、`username`、`password`

### 3.1 状态映射

- `status_mapping.todo`
- `status_mapping.in_progress`
- `status_mapping.review`
- `status_mapping.done`

### 3.2 角色映射

- `role_settings.product_manager_roles`
- `role_settings.dev_manager_roles`
- `role_settings.developer_roles`
- `role_settings.quality_roles`

### 3.3 查询范围

- `jql_filters`：系统级固定 JQL 子句，和页面 `jql` 以 `AND` 拼接。

### 3.4 Task Owner 字段（可选）

- `task_owner_field`：`customfield_12345` 或纯数字 `12345`（加载时规范为 `customfield_*`）。
- 仅**手动同步**时随 search 的 `fields` 拉取；无配置时仍可依赖 changelog 中的「Task Owner / 任务负责人」推断。

## 4. 数据来源与缓存策略

前端可选数据来源模式：

- `auto`：优先按当前 JQL 命中缓存，未命中回退到最新缓存。
- `requested`：仅命中当前 JQL 对应缓存，未命中报错。
- `latest`：直接使用最新缓存。
- `cache_id`：使用指定缓存文件（hash id）。

相关接口：

- `GET /api/cache_sources`：列出所有缓存源。
- `GET /api/cached_queries`：列出与当前配置兼容的缓存查询。
- `GET|POST /api/query?confirmed=true`：触发 JIRA 查询并写缓存。

## 5. 关键业务规则

### 5.1 解决时间（resolved_at）

「状态调整到 `status_mapping.done` 中任一状态，即视为解决时间；若存在多次进入 done，以最后一次为准」。

解析优先级：

1. changelog 中最后一次进入 done 状态的时间。
2. 若无，且当前状态属于 done：使用 `fields.resolutiondate`。
3. 若仍无：使用最后一次状态变更时间（仅当前状态属于 done 时）。

### 5.2 责任开发人（metric_owner）

1. 若 **Task Owner** 有值（来自 `fields[task_owner_field]` 或 changelog 中 Task Owner / **任务负责人**）：**`metric_owner = task_owner`**。
2. 否则按经办人与 `role_settings` 推导（产品/测试回退、开发经理等），规则见 `app/normalize.py::_derive_metric_owner`。

### 5.3 甘特图口径（member 模式）

- 泳道：责任开发人（`metric_owner`）。
- 开始时间：`developer_started_at`（首次指派给 `developer_roles` 的时间）。
- 结束时间：`resolved_at`（按 done 映射规则得到）。
- 若开始/结束任一缺失，不绘制该条任务。

## 6. 对外接口（当前）

- `GET /api/kanban`
- `GET /api/gantt`
- `GET /api/export/csv`
- `GET /api/export/xlsx`
- `GET /api/export/png`
- `GET /api/cache_sources`
- `GET /api/cached_queries`
- `GET|POST /api/query`

### 6.1 `/api/kanban` 增量输出字段

- `summary_window`：当前统计窗口（mode/label/start/end/timezone）
- `manager_summary_cards`：周期汇总卡片数据
- `manager_summary_text`：可复制周期总结文本
- `period_focus`：风险聚焦（reopened/new_issue）

## 7. 测试与质量

关键测试文件：

- `tests/test_analytics.py`
- `tests/test_config.py`
- `tests/test_normalize.py`
- `tests/test_metrics.py`
- `tests/test_routes.py`

最近一次相关回归：**52 passed**（本地执行）。

## 8. 已知限制

- 历史缓存可能缺少 `resolutiondate`，已通过多级回退补偿，但精度依赖 changelog 完整性。
- 严格开发周期口径会过滤掉未进入开发或未进入 done 的问题，导致甘特条数少于看板总数。

## 9. 下一阶段建议议题（供讨论）

1. 指标解释层：页面增加「口径说明」提示，避免误读。
2. 数据质量层：新增「时间缺失原因」诊断面板（未入开发/未入done/历史缺失）。
3. 统计扩展层：开发周期中位数、95分位、按优先级分层统计。
4. 流程对齐层：支持「已验证/已发布」等企业状态的二级里程碑图。
