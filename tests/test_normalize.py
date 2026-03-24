from datetime import datetime, timezone, timedelta

from app.normalize import build_status_groups, determine_column, extract_timeline, filter_cards, normalize_issue, parse_datetime


def test_parse_datetime_handles_offset_without_colon():
    """JIRA returns +0800 style offsets; fromisoformat needs +08:00."""
    result = parse_datetime("2026-03-03T10:39:16.000+0800")
    assert result is not None
    assert result == datetime(2026, 3, 3, 10, 39, 16, tzinfo=timezone(timedelta(hours=8)))


def test_parse_datetime_handles_offset_with_colon():
    result = parse_datetime("2026-03-03T10:39:16.000+08:00")
    assert result is not None
    assert result == datetime(2026, 3, 3, 10, 39, 16, tzinfo=timezone(timedelta(hours=8)))


def test_parse_datetime_handles_z_suffix():
    result = parse_datetime("2026-03-03T10:39:16.000Z")
    assert result is not None
    assert result.utcoffset() == timedelta(0)


def test_determine_column():
    assert determine_column("Done") == "Done"
    assert determine_column("In Progress") == "In Progress"
    assert determine_column("审核中") == "审核中"
    assert determine_column("Open") == "To Do"


def test_extract_timeline_from_histories():
    issue = {
        "fields": {"created": "2026-02-01T08:00:00.000+00:00"},
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-02T08:00:00.000+00:00",
                    "items": [{"field": "assignee", "toString": "Alice"}],
                },
                {
                    "created": "2026-02-03T08:00:00.000+00:00",
                    "items": [{"field": "status", "toString": "In Progress"}],
                },
                {
                    "created": "2026-02-04T08:00:00.000+00:00",
                    "items": [{"field": "status", "toString": "Done"}],
                },
            ]
        },
    }
    timeline = extract_timeline(issue)
    assert timeline["created_at"] is not None
    assert timeline["product_assigned_at"] is not None
    assert timeline["in_progress_at"] is not None
    assert timeline["resolved_at"] is not None


def test_filter_cards_with_multiple_conditions():
    cards = [
        {"key": "A-1", "summary": "alpha", "assignee": "Alice", "priority": "High"},
        {"key": "B-2", "summary": "beta", "assignee": "Bob", "priority": "Low"},
    ]
    result = filter_cards(cards, assignee="Alice", priority="High", keyword="alpha")
    assert len(result) == 1
    assert result[0]["key"] == "A-1"


def test_filter_cards_matches_metric_owner():
    """Filtering by assignee should also match cards where metric_owner equals the filter value."""
    cards = [
        {"key": "A-1", "summary": "alpha", "assignee": "测试A", "metric_owner": "开发X", "priority": "High"},
        {"key": "B-2", "summary": "beta", "assignee": "开发X", "metric_owner": "开发X", "priority": "Low"},
        {"key": "C-3", "summary": "gamma", "assignee": "开发Y", "metric_owner": "开发Y", "priority": "High"},
    ]
    result = filter_cards(cards, assignee="开发X")
    assert len(result) == 2
    keys = {card["key"] for card in result}
    assert keys == {"A-1", "B-2"}


def test_determine_column_resolved_by_resolutiondate_when_status_unmapped():
    """自定义 done 未列出「已解决」等状态时，有 resolutiondate 仍应进 Done 列。"""
    groups = build_status_groups(
        {
            "todo": ["Open", "已分配"],
            "in_progress": ["开发中"],
            "review": ["审核中"],
            "done": ["已关闭", "Resolved"],
        }
    )
    assert determine_column("已解决", groups, resolution_date="2025-08-29T17:59:26.000+0800") == "Done"
    assert determine_column("未知状态", groups, resolution_date="2025-01-01T00:00:00.000+0800") == "Done"
    assert determine_column("未知状态", groups, resolution_date=None) == "To Do"


def test_determine_column_with_custom_status_mapping():
    status_mapping = {
        "todo": ["已分配"],
        "in_progress": ["开发中"],
        "review": ["审核中"],
        "done": ["已关闭"],
    }
    assert determine_column("已分配", None) == "To Do"
    assert determine_column("开发中", None) == "To Do"
    assert determine_column("开发中", status_groups=None) == "To Do"

    groups = build_status_groups(status_mapping)
    assert determine_column("已分配", groups) == "To Do"
    assert determine_column("开发中", groups) == "In Progress"
    assert determine_column("审核中", groups) == "审核中"
    assert determine_column("已关闭", groups) == "Done"


def test_extract_timeline_with_role_settings():
    issue = {
        "fields": {"created": "2026-02-01T08:00:00.000+00:00"},
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-02T08:00:00.000+00:00",
                    "items": [{"field": "assignee", "to": "humeng", "toString": "胡梦"}],
                },
                {
                    "created": "2026-02-03T08:00:00.000+00:00",
                    "items": [{"field": "assignee", "to": "hushengquan", "toString": "胡圣泉"}],
                },
            ]
        },
    }
    timeline = extract_timeline(
        issue,
        role_settings={
            "product_manager_roles": ["humeng"],
            "dev_manager_roles": ["hushengquan"],
            "developer_roles": ["hushengquan", "胡圣泉"],
        },
    )
    assert timeline["product_assigned_at"] == "2026-02-02T08:00:00.000+00:00"
    assert timeline["product_assigned_to"] == "胡梦"
    assert timeline["dev_manager_assigned_at"] == "2026-02-03T08:00:00.000+00:00"
    assert timeline["dev_manager_assigned_to"] == "胡圣泉"
    assert timeline["developer_started_at"] == "2026-02-03T08:00:00.000+00:00"


def test_normalize_issue_metric_owner_prefers_last_non_pm_assignee():
    issue = {
        "key": "ABC-99",
        "fields": {
            "summary": "workflow",
            "status": {"name": "Done"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "胡梦", "name": "humeng"},
            "issuetype": {"name": "缺陷"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-02T00:00:00+00:00",
                    "items": [{"field": "assignee", "to": "dev_a", "toString": "开发A"}],
                },
                {
                    "created": "2026-02-03T00:00:00+00:00",
                    "items": [{"field": "assignee", "to": "humeng", "toString": "胡梦"}],
                },
            ]
        },
    }

    card = normalize_issue(
        issue,
        base_url="https://jira.example.com",
        role_settings={"product_manager_roles": ["humeng", "胡梦"]},
    )
    assert card["assignee"] == "胡梦"
    assert card["metric_owner"] == "开发A"


def test_normalize_issue_metric_owner_quality_fallback_to_last_developer():
    issue = {
        "key": "ABC-100",
        "fields": {
            "summary": "qa handoff",
            "status": {"name": "审核中"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "品质A", "name": "qa_a"},
            "issuetype": {"name": "缺陷"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-02T00:00:00+00:00",
                    "items": [{"field": "assignee", "to": "dev_a", "toString": "开发A"}],
                },
                {
                    "created": "2026-02-03T00:00:00+00:00",
                    "items": [{"field": "assignee", "to": "qa_a", "toString": "品质A"}],
                },
            ]
        },
    }

    card = normalize_issue(
        issue,
        base_url="https://jira.example.com",
        role_settings={
            "developer_roles": ["dev_a", "开发A"],
            "quality_roles": ["qa_a", "品质A"],
        },
    )
    assert card["assignee"] == "品质A"
    assert card["metric_owner"] == "开发A"


def test_extract_timeline_uses_resolutiondate_when_current_status_is_done():
    issue = {
        "fields": {
            "created": "2026-02-01T08:00:00.000+00:00",
            "status": {"name": "主干已解决"},
            "resolutiondate": "2026-02-06T09:30:00.000+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-02T08:00:00.000+00:00",
                    "items": [{"field": "assignee", "toString": "Alice"}],
                }
            ]
        },
    }
    timeline = extract_timeline(
        issue,
        status_groups={
            "todo": {"open"},
            "in_progress": {"正在解决"},
            "review": {"审核中"},
            "done": {"主干已解决", "已关闭"},
        },
    )
    assert timeline["resolved_at"] == "2026-02-06T09:30:00.000+00:00"


def test_extract_timeline_uses_current_done_status_transition_when_resolutiondate_missing():
    issue = {
        "fields": {
            "created": "2026-02-01T08:00:00.000+00:00",
            "status": {"name": "主干已解决"},
            "resolutiondate": None,
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-04T10:00:00.000+00:00",
                    "items": [{"field": "status", "toString": "审核中"}],
                },
                {
                    "created": "2026-02-05T11:00:00.000+00:00",
                    "items": [{"field": "status", "toString": "主干已解决"}],
                },
            ]
        },
    }
    timeline = extract_timeline(
        issue,
        status_groups={
            "todo": {"open"},
            "in_progress": {"正在解决"},
            "review": {"审核中"},
            "done": {"主干已解决", "已关闭"},
        },
    )
    assert timeline["resolved_at"] == "2026-02-05T11:00:00.000+00:00"


def test_extract_timeline_uses_latest_status_change_as_done_fallback():
    issue = {
        "fields": {
            "created": "2026-02-01T08:00:00.000+00:00",
            "status": {"name": "主干已解决"},
            "resolutiondate": None,
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-04T10:00:00.000+00:00",
                    "items": [{"field": "status", "toString": "审核中"}],
                },
                {
                    "created": "2026-02-05T11:00:00.000+00:00",
                    "items": [{"field": "status", "toString": "已验证"}],
                },
            ]
        },
    }
    timeline = extract_timeline(
        issue,
        status_groups={
            "todo": {"open"},
            "in_progress": {"正在解决"},
            "review": {"审核中"},
            "done": {"主干已解决", "已关闭"},
        },
    )
    assert timeline["resolved_at"] == "2026-02-05T11:00:00.000+00:00"


def test_extract_timeline_collects_reopened_events():
    issue = {
        "fields": {
            "created": "2026-02-01T08:00:00.000+00:00",
            "status": {"name": "审核中"},
            "resolutiondate": None,
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-03T08:00:00.000+00:00",
                    "items": [{"field": "status", "fromString": "Done", "toString": "审核中"}],
                }
            ]
        },
    }
    timeline = extract_timeline(
        issue,
        status_groups={
            "todo": {"open"},
            "in_progress": {"正在解决"},
            "review": {"审核中"},
            "done": {"done", "已关闭"},
        },
    )
    assert timeline["reopened_events"] == ["2026-02-03T08:00:00.000+00:00"]


def test_extract_timeline_resolved_at_uses_last_done_transition():
    """When an issue goes Done -> Reopened -> Done, resolved_at should be the last Done time."""
    issue = {
        "fields": {
            "created": "2026-02-01T08:00:00.000+00:00",
            "status": {"name": "Done"},
            "resolutiondate": None,
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-03T08:00:00.000+00:00",
                    "items": [{"field": "status", "fromString": "Open", "toString": "Done"}],
                },
                {
                    "created": "2026-02-04T08:00:00.000+00:00",
                    "items": [{"field": "status", "fromString": "Done", "toString": "In Progress"}],
                },
                {
                    "created": "2026-02-06T10:00:00.000+00:00",
                    "items": [{"field": "status", "fromString": "In Progress", "toString": "Done"}],
                },
            ]
        },
    }
    timeline = extract_timeline(issue)
    assert timeline["resolved_at"] == "2026-02-06T10:00:00.000+00:00"
    assert timeline["reopened_events"] == ["2026-02-04T08:00:00.000+00:00"]


def test_metric_owner_quality_fallback_without_developer_roles():
    """When quality_roles is set but developer_roles is empty, metric_owner should
    fall back to the last non-QA/non-PM/non-DM assignee in changelog."""
    issue = {
        "key": "QA-1",
        "fields": {
            "summary": "qa no dev roles",
            "status": {"name": "审核中"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "李启沆", "name": "liqihang"},
            "issuetype": {"name": "缺陷"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-02T00:00:00+00:00",
                    "items": [{"field": "assignee", "to": "dev_x", "toString": "开发X"}],
                },
                {
                    "created": "2026-02-03T00:00:00+00:00",
                    "items": [{"field": "assignee", "to": "liqihang", "toString": "李启沆"}],
                },
            ]
        },
    }

    card = normalize_issue(
        issue,
        base_url="https://jira.example.com",
        role_settings={
            "quality_roles": ["liqihang", "李启沆"],
            # developer_roles intentionally omitted
        },
    )
    assert card["assignee"] == "李启沆"
    assert card["metric_owner"] == "开发X"


def test_normalize_issue_metric_owner_when_assignee_is_dev_manager():
    """经办人为开发经理时：任务负责人与 Jira 经办人一致（不从 changelog 回退）。"""
    issue = {
        "key": "DM-1",
        "fields": {
            "summary": "todo item",
            "status": {"name": "Open"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "胡圣泉", "name": "hushengquan"},
            "issuetype": {"name": "任务"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-02T00:00:00+00:00",
                    "items": [{"field": "assignee", "to": "xieyi", "toString": "谢屹"}],
                },
                {
                    "created": "2026-02-03T00:00:00+00:00",
                    "items": [{"field": "assignee", "to": "hushengquan", "toString": "胡圣泉"}],
                },
            ]
        },
    }
    card = normalize_issue(
        issue,
        base_url="https://jira.example.com",
        role_settings={
            "dev_manager_roles": ["hushengquan", "胡圣泉"],
            "developer_roles": ["xieyi", "谢屹"],
            "product_manager_roles": ["pm", "产品"],
        },
    )
    assert card["assignee"] == "胡圣泉"
    assert card["metric_owner"] == "胡圣泉"


def test_task_owner_custom_field_overrides_metric_owner():
    issue = {
        "key": "TO-1",
        "fields": {
            "summary": "with task owner cf",
            "status": {"name": "Open"},
            "priority": {"name": "Medium"},
            "assignee": {"displayName": "胡圣泉", "name": "hushengquan"},
            "customfield_99999": {"displayName": "张睿妍", "name": "zhangruiyan"},
            "issuetype": {"name": "任务"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {"histories": []},
    }
    card = normalize_issue(
        issue,
        base_url="https://jira.example.com",
        role_settings={"dev_manager_roles": ["hushengquan"]},
        task_owner_field="customfield_99999",
    )
    assert card["metric_owner"] == "张睿妍"
    assert card["task_owner"] == "张睿妍"
    assert card["task_owner_source"] == "jira_field"
    assert card["task_owner_jira_field"] == "customfield_99999"


def test_task_owner_from_changelog_when_fields_missing():
    """fields 无 customfield 时，从 changelog 取最后一次 Task Owner 变更。"""
    issue = {
        "key": "TOC-1",
        "fields": {
            "summary": "x",
            "status": {"name": "Open"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "经理", "name": "m"},
            "issuetype": {"name": "任务"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-02T00:00:00+00:00",
                    "items": [{"field": "Task Owner", "fieldtype": "custom", "to": "u1", "toString": "张三"}],
                },
                {
                    "created": "2026-02-03T00:00:00+00:00",
                    "items": [{"field": "Task Owner", "fieldtype": "custom", "to": "u2", "toString": "李四"}],
                },
            ]
        },
    }
    card = normalize_issue(issue, base_url="https://jira.example.com")
    assert card["task_owner"] == "李四"
    assert card["metric_owner"] == "李四"
    assert card["task_owner_source"] == "changelog"
    assert card["task_owner_jira_field"] is None


def test_task_owner_from_changelog_chinese_field_name():
    """changelog 中 field 为中文「任务负责人」时与英文 Task Owner 同等处理。"""
    issue = {
        "key": "ZWCAD-44464",
        "fields": {
            "summary": "x",
            "status": {"name": "Open"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "杨将来", "name": "yangjianglai"},
            "issuetype": {"name": "任务"},
            "created": "2025-12-01T00:00:00+08:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2025-12-08T16:33:51.000+0800",
                    "items": [
                        {
                            "field": "任务负责人",
                            "fieldtype": "custom",
                            "from": None,
                            "fromString": None,
                            "to": "chenxing",
                            "toString": "陈兴",
                        }
                    ],
                },
            ]
        },
    }
    card = normalize_issue(issue, base_url="https://jira.example.com")
    assert card["task_owner"] == "陈兴"
    assert card["metric_owner"] == "陈兴"
    assert card["task_owner_source"] == "changelog"


def test_task_owner_fields_preferred_over_changelog():
    issue = {
        "key": "TOC-2",
        "fields": {
            "summary": "x",
            "status": {"name": "Open"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "经理", "name": "m"},
            "customfield_99999": {"displayName": "字段快照", "name": "snap"},
            "issuetype": {"name": "任务"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-04T00:00:00+00:00",
                    "items": [{"field": "Task Owner", "fieldtype": "custom", "toString": "历史里更新"}],
                },
            ]
        },
    }
    card = normalize_issue(
        issue,
        base_url="https://jira.example.com",
        task_owner_field="customfield_99999",
    )
    assert card["task_owner"] == "字段快照"
    assert card["metric_owner"] == "字段快照"
    assert card["task_owner_source"] == "jira_field"


def test_task_owner_changelog_cleared_falls_back_to_derive():
    """最后一次 Task Owner 被清空时，不再用 changelog，回退经办人推导。"""
    issue = {
        "key": "TOC-3",
        "fields": {
            "summary": "x",
            "status": {"name": "Open"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "经办人王", "name": "wang"},
            "issuetype": {"name": "任务"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-02T00:00:00+00:00",
                    "items": [{"field": "Task Owner", "fieldtype": "custom", "toString": "曾有负责人"}],
                },
                {
                    "created": "2026-02-05T00:00:00+00:00",
                    "items": [{"field": "Task Owner", "fieldtype": "custom", "toString": "-", "to": None}],
                },
            ]
        },
    }
    card = normalize_issue(issue, base_url="https://jira.example.com")
    assert card["task_owner"] is None
    assert card["metric_owner"] == "经办人王"
    assert card["task_owner_source"] is None
    assert card["task_owner_jira_field"] is None


def test_metric_owner_quality_skips_pm_and_dm_in_fallback():
    """Fallback should skip PM and DM assignees, returning the developer."""
    issue = {
        "key": "QA-2",
        "fields": {
            "summary": "qa skip pm dm",
            "status": {"name": "审核中"},
            "priority": {"name": "Medium"},
            "assignee": {"displayName": "品质B", "name": "qa_b"},
            "issuetype": {"name": "缺陷"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-01T09:00:00+00:00",
                    "items": [{"field": "assignee", "to": "pm_a", "toString": "产品A"}],
                },
                {
                    "created": "2026-02-02T09:00:00+00:00",
                    "items": [{"field": "assignee", "to": "dm_a", "toString": "经理A"}],
                },
                {
                    "created": "2026-02-03T09:00:00+00:00",
                    "items": [{"field": "assignee", "to": "dev_y", "toString": "开发Y"}],
                },
                {
                    "created": "2026-02-04T09:00:00+00:00",
                    "items": [{"field": "assignee", "to": "qa_b", "toString": "品质B"}],
                },
            ]
        },
    }

    card = normalize_issue(
        issue,
        base_url="https://jira.example.com",
        role_settings={
            "product_manager_roles": ["pm_a", "产品A"],
            "dev_manager_roles": ["dm_a", "经理A"],
            "quality_roles": ["qa_b", "品质B"],
        },
    )
    assert card["metric_owner"] == "开发Y"
