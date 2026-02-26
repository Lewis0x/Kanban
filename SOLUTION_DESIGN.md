# 方案文档

## 1. 架构概览

- 后端：Python + Flask
- 数据层：JIRA Filter/Search API + changelog
- 前端：Jinja + 原生 JavaScript
- 导出层：CSV/Excel/PNG

## 2. 模块划分

- `app/config.py`：配置加载与认证参数（含筛选器设置）
- `app/jira_client.py`：JIRA API 访问与分页
- `app/normalize.py`：issue 标准化与阶段推断
- `app/metrics.py`：成员指标与甘特数据构建
- `app/main.py`：路由、接口、导出

## 3. 接口设计

- `GET /api/filters`：获取筛选器列表（可返回默认筛选器）
- `GET /api/kanban?filter_id=&assignee=&priority=&q=&jql=`：按筛选器取 issue 并本地构建三列看板
- `GET /api/gantt?filter_id=&mode=member|sprint&assignee=&priority=&q=&jql=`：获取甘特数据
- `GET /api/export/csv?...`：导出明细 CSV
- `GET /api/export/xlsx?...`：导出明细+统计 Excel
- `GET /api/export/png?...`：导出甘特 PNG

## 4. 关键规则

### 4.1 状态映射

- To Do：`to do/open/backlog/selected for development`
- In Progress：`in progress/development/in review/code review/testing`
- Done：`done/resolved/closed`

### 4.2 changelog 时间推断

- 历史按时间升序处理
- `assignee` 第一次变更作为 `product_assigned_at`
- `assignee` 第二次变更作为 `dev_manager_assigned_at`
- `status` 首次进入关键状态记录节点时间

## 5. 异常与稳定性

- 401/403：认证与权限错误
- 429：速率限制
- 5xx：JIRA 服务异常
- 全部输出统一 JSON 错误格式

## 6. 测试策略

- 单元测试：状态映射、时间推断、指标计算
- 接口测试：筛选、返回结构、导出行为
- 客户端测试：分页、异常转换

## 7. 发布与运维

- 使用 `flask run` 启动
- 通过配置文件管理连接参数
- 日志输出到控制台，便于部署前排查
