# Jira Sprint Kanban

用于跟踪部门成员问题解决进展的只读看板系统，数据来源为 JIRA API（通过 JQL 拉取 Issue，系统在本地构建三列看板）。

## 功能

- 冲刺看板：按 `To Do / In Progress / Done` 三列展示问题
- 统一筛选：JQL、负责人、优先级、关键字
- 甘特视图：按成员或按 Sprint 展示问题生命周期时间轴
- 指标：解决率、平均 Lead Time、WIP、优先级加权进度
- 导出：CSV、Excel、PNG

## 快速开始

### 一键启动（Windows）

- 双击 `start_kanban.bat`，或在 Kanban 目录执行 `.\start_kanban.ps1`。
- 脚本会自动创建 `.venv`、安装依赖并启动 Flask（`http://127.0.0.1:5000`）。
- 首次使用仍需按下方说明配置 `config/jira_auth.yaml`。

### 手动启动

```powershell
cd D:\Work\Lewis\JiraSprintKanban
py -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy config\jira_auth.example.yaml config\jira_auth.yaml
.\.venv\Scripts\python -m flask --app app.main run --debug
```

浏览器访问 `http://127.0.0.1:5000`。

## 使用说明

### 1. 首次配置

1. 复制模板：`copy config\jira_auth.example.yaml config\jira_auth.yaml`
2. 编辑 `config/jira_auth.yaml`，填写：
	- `base_url`: JIRA 域名
	- `username`: 账号（通常为邮箱）
	- `password`: 账号密码
	- `jql_filters`: 预置 JQL 过滤条件列表（可选）
	- `role_settings`（`product_manager_roles` / `dev_manager_roles` / `developer_roles` / `quality_roles`）：用于从经办人历史推断**任务负责人**（当前经办人为**产品 / 测试**等时仍会从 changelog 回退到开发；**开发经理作为经办人时不再回退**，与 Jira 经办人一致）。
	- `task_owner_field`（可选）：与 **Task Owner** 对应的 Jira REST 自定义字段 id。可写 **`customfield_12345`** 或**纯数字** `12345`（会规范为 `customfield_12345`）。仅在**手动从 Jira 同步**时随 `GET /rest/api/2/search` 的 `fields` 拉取；**刷新看板不访问 Jira**。
3. 启动服务：`python -m flask --app app.main run --debug`

### 1.1 任务负责人：全链路「字段」与匹配逻辑

以下均指代码里最终用于看板/指标/周期总结的 **`metric_owner`**（及卡片上的「任务负责人」）；**Jira 经办人**始终单独取自 `fields.assignee`，不参与覆盖 `metric_owner`（除非未配置 Task Owner 且推导结果就是经办人）。

| 步骤 | 位置 | 逻辑 |
|------|------|------|
| **1. 拉取 Issue** | `app/jira_client.py` | 同步时若配置了 `task_owner_field`（已规范为 `customfield_*`），将其**追加**到 `search` 的 `fields`；否则不请求任何自定义字段。 |
| **2. Task Owner 自定义字段** | `app/normalize.py` → `_extract_task_owner_display` | 读 `fields[task_owner_field]`：① **dict**（用户选择器）→ `displayName`，否则 `name`；② **非空字符串**→ 原样；③ **非空 list**→ 取第一个元素按 ①/② 解析。 |
| **2b. Task Owner 回退（changelog）** | `app/normalize.py` → `_extract_latest_task_owner_from_changelog` | 若上一步未解析到值：按 **`histories[].created` 时间正序**扫描 `items`，匹配 **`field` 名为 `Task Owner`（忽略大小写）或 `任务负责人`** 的变更；每次用 `toString`，否则 `to`；**空字符串或 `-` 视为清空**。取**最后一次变更后的结果**作为 `task_owner`（与 Jira 当前逻辑一致时可替代未请求的 `customfield_*`）。 |
| **3. 覆盖 metric_owner** | `app/normalize.py` → `normalize_issue` | 若 **`task_owner` 有值**，则 **`metric_owner = task_owner`**，**不再**用经办人推导。 |
| **4. 经办人推导（无 Task Owner 时）** | `app/normalize.py` → `_derive_metric_owner` | 用 `assignee.displayName`、`assignee.name`（login）与 `role_settings` 做集合匹配（**全部转小写**后比较，中文名不变）。 |
| **4a. 当前经办人 ∈ `quality_roles`** | 同上 | 若配置了 **`developer_roles`**：在 changelog 中按**时间倒序**找第一条 `assignee` 变更，其 `toString`/`to` 与 **`developer_roles`** 有交集 → 返回该 `toString`。否则在 changelog 倒序中找第一个「经办人 ∉ (产品∪开发经理∪测试)」→ 返回；否则返回当前经办人显示名。 |
| **4b. 未配置 `product_manager_roles`** | 同上 | **直接返回**当前经办人显示名。 |
| **4c. 当前经办人 ∉ `product_manager_roles`** | 同上 | **直接返回**当前经办人显示名（含开发经理、开发等）。 |
| **4d. 当前经办人 ∈ `product_manager_roles`** | 同上 | 若配置了 **`developer_roles`**：changelog 倒序找最近一次经办人落在 **`developer_roles`** → 返回。否则 changelog 倒序找第一个「经办人 ∉ 产品角色」→ 返回。否则返回当前经办人。 |
| **5. `developer_roles` 来源** | `app/config.py` → `load_config` | ① `role_settings.developer_roles`；若为空则 ② 从 **`teams[].members`** 自动生成并去掉同时在 产品/开发经理/测试 列表里的人名；③ 追加 **`developer_role_logins`**（Jira 登录名，用于与 changelog 里 `to` 匹配）。 |
| **6. 角色集合** | `app/normalize.py` → `build_role_groups` | `product_manager_roles` / `dev_manager_roles` / `developer_roles` / `quality_roles` 均为配置项**去空、转小写**后的集合，用于上述交集判断。 |
| **7. 时间轴里的经办人** | `app/normalize.py` → `extract_timeline` | 仅影响**详情时间线**（产品分配、开发经理分配、开发开始等），**不**改写 `metric_owner`。匹配规则：`assignee` 变更的 `toString`/`to`（小写）与对应角色集合是否有交集；无 `pm_roles` 时产品分配取**第 1 次**经办变更；无 `dm_roles` 时开发经理分配取**第 2 次**经办变更。 |
| **8. 看板卡片展示** | `static/app.js` | 副标题：`metric_owner \|\| assignee`；详情：**任务负责人** = `metric_owner \|\| assignee`，**Jira 经办人** = `assignee`。 |
| **9. 筛选「负责人」** | `app/normalize.py` → `filter_cards` | 下拉为经办人与 `metric_owner` 的并集；过滤时 **`assignee` 或 `metric_owner` 等于所选**即保留。 |
| **10. 成员指标 / 甘特 member** | `app/metrics.py` | 分组键：`metric_owner \|\| assignee \|\| Unassigned`；甘特泳道同左。 |
| **11. 周期总结按人分组** | `app/analytics.py` | `_owner_of(card)` = `metric_owner \|\| assignee \|\| 未分配`。 |

**配置后请务必重新执行一次「从 Jira 同步」**，旧缓存里没有对应 `customfield_*` 时，看板仍无法从 fields 读到 Task Owner（可依赖 changelog 回退）。

### 2. 看板操作

1. 打开页面后可在 `自定义JQL` 输入框填写查询条件（可选）
2. 系统自动加载三列看板：`To Do / In Progress / Done`
4. 可使用筛选项：负责人、优先级、关键字
5. 点击任一卡片可在右侧查看详情与时间节点：
	- 创建时间
	- 产品分配时间（首次 assignee 变更）
	- 开发经理分配时间（第二次 assignee 变更）
	- 进入 In Progress 时间
	- 解决时间（若多次进入 Done，以最后一次进入 Done 的时间为准）

### 2.1 周期总结口径

- `本周期分配`：统计周期窗口内 `dev_manager_assigned_at` 的问题数
- `本周期解决`（可复制总结里的「已解决问题」）：统计周期窗口内 **`resolved_at` 或 `closed_at`** 任一落在窗口内的问题数。`resolved_at` 为最后一次进入 `status_mapping.done` 的时间；`closed_at` 为进入 **「已关闭」/ Closed**（且该状态在 done 组内）的时间，用于「先已解决、后已关闭」分步流程——仅关闭落在本周期时也会进总结。
- `本周期未解决`：统计周期窗口内被开发经理分配且 **既无 `resolved_at` 也无 `closed_at`**（均未进入终态时间轴）的问题数
- `重开事件`：统计周期窗口内 `reopened_events` 的事件次数（同一问题可多次计数）
- `New Issue`：统计周期窗口内 `created_at` 的问题数
- `净变化`：`New Issue - 本周期解决`

### 2.2 周期总结可复制文本模板

页面上「复制总结」使用的多行文本由 **`config/manager_summary_template.yaml`** 中的 `strings` 段生成。可直接编辑该文件调整措辞与排版（占位符说明见文件内注释）；**修改后请重启 Flask**。

- 若文件不存在或某键缺失，将使用 `app/analytics.py` 内 `_BUILTIN_SUMMARY_STRINGS` 的默认文案。
- 「已解决问题」列表为**两级**：`resolved_status_group`（按 Jira 状态）→ `resolved_owner_group`（按负责人）→ `item_resolved`；状态名为空时归为「（无状态）」，状态分组按字母序（无状态排最后）。
- Issue 的 `summary` 等字段若含 `{` / `}`，程序会自动转义，无需在模板中特殊处理；若要在模板里输出**字面量**花括号，请写成 `{{` 与 `}}`（Python `str.format` 规则）。

### 3. 甘特图操作

1. 在 `mode` 切换甘特维度：
	- `member`: 按成员泳道
	- `sprint`: 按 Sprint 泳道
2. 甘特图与看板共用同一筛选条件
3. 刷新后可查看当前筛选范围内的问题时间条

### 3.1 JQL 预览

- 页面新增 `自定义JQL（可选）` 输入框，可输入临时查询子句
- 页面会显示 `JQL 预览（只读）`，用于查看最终拼接语句
- 最终语句规则：`config.jql_filters` + 页面输入 `jql`（均以 `AND` 拼接）

### 4. 导出说明

- `CSV`：导出问题明细
- `Excel`：导出问题明细 + 成员指标
- `PNG`：导出当前筛选条件下的甘特图快照

导出内容遵循当前页面筛选条件（JQL、负责人、优先级、关键字、甘特模式）。

### 5. 常见问题

- 401/403：检查 `username/password` 是否正确，确认对问题有访问权限
- 429：JIRA 限流，稍后重试
- 时间节点为空：该问题在 changelog 中没有对应状态/指派变更记录
- 周期总结为 0：确认时间字段格式是否可解析（系统兼容 `Z`、`+08:00`、`+0800`）

## 配置

编辑 `config/jira_auth.yaml`：

- `base_url`: JIRA 地址，如 `https://your-company.atlassian.net`
- `username`: 用户名或邮箱
- `password`: 用户密码
- `verify_ssl`: 是否校验证书
- `request_timeout_seconds`: 请求超时
- `jql_filters`: 预置 JQL 条件数组，系统会自动以 `AND` 拼接各条件

示例：

```yaml
base_url: https://jira.example.com/
username: your-user
password: your-password
verify_ssl: true
request_timeout_seconds: 30
jql_filters:
	- project = CAD
	- issuetype in (Bug, Task, Story)
```

## 测试

```powershell
.\.venv\Scripts\python -m pytest -q
```
