# 开发文档 — Jira Sprint Kanban

## 0. 最新迭代（2026-02-25）
- 完成 A 方案界面重构（单页分区）：
  - 顶部状态栏：数据源状态、最近刷新时间、刷新与导出入口
  - 筛选区改为“基础常驻 + 高级折叠”（高级区承载数据源模式/缓存ID/JQL预览）
  - 主工作区改为 Kanban 与详情侧栏 70/30 布局
  - 分析区改为默认折叠，展开后显示风险聚焦/成员指标/甘特视图
  - 周期支持 `custom`，仅在自定义周期时展示起止日期输入
- 前端交互补齐：
  - 新增“高级筛选”折叠按钮
  - 新增“分析区”展开/收起按钮
  - 新增“最近刷新时间”实时更新
- 完成“界面与数据逻辑解耦”第一阶段：
  - 新增分析层 `app/analytics.py`（周期汇总、重开事件统计、风险聚焦明细）
  - 新增周期窗口层 `app/period.py`（本周/最近7天/Sprint/自定义区间）
  - `app/main.py` 路由改为组装响应，口径计算从路由逻辑下沉到分析层
- 新增周期总结能力（`/api/kanban` 增量字段）：
  - `summary_window`
  - `manager_summary_cards`
  - `manager_summary_text`
  - `period_focus`
- 新增风险聚焦下钻：
  - `Reopened`：事件数 + 问题明细（重开次数、最后重开时间）
  - `New Issue`：当前按创建时间口径统计（保留后续自定义字段接入位）
- 前端重构为 `apiClient + state + render` 组织方式，新增：
  - 周期选择（本周/最近7天/当前Sprint）
  - 自定义 `start/end` 时间输入
  - 周期总结卡片与“复制总结”交互
  - 风险聚焦双表（Reopened/New Issue）
- 测试新增/更新：
  - 新增 `tests/test_analytics.py`
  - 更新 `tests/test_routes.py`（验证摘要合同与自定义窗口）
  - 更新 `tests/test_normalize.py`（重开事件提取）
  - 当前全量回归：`31 passed`

## 1. 当前目标与范围
- 只读看板系统，基于 JQL + 本地缓存展示问题进展，不直接写回 JIRA。
- 核心视图：看板、成员指标、甘特图、导出（CSV/Excel/PNG）。
- 当前重点是“准确反映问题解决责任人及开发周期”。

## 2. 架构总览
- 后端：Flask（`app/main.py`）
- 数据获取：JIRA REST API `/rest/api/2/search`（`app/jira_client.py`）
- 本地缓存：`storage/jira_query_cache/*.json`
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
“状态调整到 `status_mapping.done` 中任一状态，即视为解决时间”。

解析优先级：
1. changelog 中首次进入 done 状态的时间。
2. 若无，且当前状态属于 done：使用 `fields.resolutiondate`。
3. 若仍无：使用最后一次状态变更时间（仅当前状态属于 done 时）。

### 5.2 责任开发人（metric_owner）
- 默认：`metric_owner = 当前 assignee`。
- 若当前 assignee 属于 `quality_roles`：回溯 assignee 历史，取最后一个 `developer_roles`。
- 若当前 assignee 属于 `product_manager_roles`：优先回溯最后一个 `developer_roles`；若无再回溯最后一个非产品角色。

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
- 关键测试文件：
  - `tests/test_analytics.py`
  - `tests/test_config.py`
  - `tests/test_jira_client.py`
  - `tests/test_normalize.py`
  - `tests/test_metrics.py`
  - `tests/test_routes.py`
- 最近一次相关回归：通过（本地执行）。

## 8. 已知限制
- 历史缓存可能缺少 `resolutiondate`，已通过多级回退补偿，但精度依赖 changelog 完整性。
- 严格开发周期口径会过滤掉未进入开发或未进入 done 的问题，导致甘特条数少于看板总数。

## 9. 下一阶段建议议题（供讨论）
1. 指标解释层：页面增加“口径说明”提示，避免误读。
2. 数据质量层：新增“时间缺失原因”诊断面板（未入开发/未入done/历史缺失）。
3. 统计扩展层：开发周期中位数、95分位、按优先级分层统计。
4. 流程对齐层：支持“已验证/已发布”等企业状态的二级里程碑图。
