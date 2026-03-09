# Jira Sprint Kanban

用于跟踪部门成员问题解决进展的只读看板系统，数据来源为 JIRA API（通过 JQL 拉取 Issue，系统在本地构建三列看板）。

## 功能

- 冲刺看板：按 `To Do / In Progress / Done` 三列展示问题
- 统一筛选：JQL、负责人、优先级、关键字
- 甘特视图：按成员或按 Sprint 展示问题生命周期时间轴
- 指标：解决率、平均 Lead Time、WIP、优先级加权进度
- 导出：CSV、Excel、PNG

## 快速开始

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
3. 启动服务：`python -m flask --app app.main run --debug`

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
- `本周期解决`：统计周期窗口内 `resolved_at` 的问题数（`resolved_at` 取最后一次进入 Done 的时间）
- `本周期未解决`：统计周期窗口内被开发经理分配且当前 `resolved_at` 为空的问题数
- `重开事件`：统计周期窗口内 `reopened_events` 的事件次数（同一问题可多次计数）
- `New Issue`：统计周期窗口内 `created_at` 的问题数
- `净变化`：`New Issue - 本周期解决`

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
