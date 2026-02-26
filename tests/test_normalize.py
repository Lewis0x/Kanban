from app.normalize import determine_column, extract_timeline, filter_cards, normalize_issue, parse_datetime


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
                    "items": [{"field": "status", "toString": "解决中"}],
                },
                {
                    "created": "2026-02-04T08:00:00.000+00:00",
                    "items": [{"field": "status", "fromString": "审核中", "toString": "主干已解决"}],
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
    from app.normalize import build_status_groups

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
                    "items": [
                        {
                            "field": "assignee",
                            "from": "hushengquan",
                            "fromString": "胡圣泉",
                            "to": "xieyi",
                            "toString": "谢屹",
                        }
                    ],
                },
            ]
        },
    }
    timeline = extract_timeline(
        issue,
        role_settings={
            "product_manager_roles": ["humeng"],
            "dev_manager_roles": ["hushengquan"],
            "developer_roles": ["xieyi", "谢屹"],
        },
        teams=[{"id": "algo", "name": "算法组", "members": ["xieyi", "谢屹"]}],
    )
    assert timeline["product_assigned_at"] == "2026-02-02T08:00:00.000+00:00"
    assert timeline["product_assigned_to"] == "胡梦"
    assert timeline["dev_manager_assigned_at"] == "2026-02-03T08:00:00.000+00:00"
    assert timeline["dev_manager_assigned_from"] == "胡圣泉"
    assert timeline["dev_manager_assigned_to"] == "谢屹"
    assert timeline["developer_started_at"] == "2026-02-03T08:00:00.000+00:00"


def test_extract_timeline_uses_last_dev_manager_assignment_time():
    issue = {
        "fields": {"created": "2026-02-01T08:00:00.000+00:00"},
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-02T08:00:00.000+00:00",
                    "items": [
                        {
                            "field": "assignee",
                            "from": "hushengquan",
                            "fromString": "胡圣泉",
                            "to": "dev_a",
                            "toString": "开发A",
                        }
                    ],
                },
                {
                    "created": "2026-02-05T09:30:00.000+00:00",
                    "items": [
                        {
                            "field": "assignee",
                            "from": "hushengquan",
                            "fromString": "胡圣泉",
                            "to": "dev_a",
                            "toString": "开发A",
                        }
                    ],
                },
            ]
        },
    }

    timeline = extract_timeline(
        issue,
        role_settings={
            "dev_manager_roles": ["hushengquan", "胡圣泉"],
            "developer_roles": ["dev_a", "开发A"],
        },
        teams=[{"id": "algo", "name": "算法组", "members": ["dev_a", "开发A"]}],
    )

    assert timeline["dev_manager_assigned_at"] == "2026-02-05T09:30:00.000+00:00"
    assert timeline["dev_manager_assigned_from"] == "胡圣泉"
    assert timeline["dev_manager_assigned_to"] == "开发A"


def test_extract_timeline_dev_manager_assignment_requires_config_roles_and_team_member():
    issue = {
        "fields": {"created": "2026-02-01T08:00:00.000+00:00"},
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-04T09:00:00.000+00:00",
                    "items": [
                        {
                            "field": "assignee",
                            "from": "someone_else",
                            "fromString": "非开发经理",
                            "to": "dev_a",
                            "toString": "开发A",
                        }
                    ],
                },
                {
                    "created": "2026-02-05T09:00:00.000+00:00",
                    "items": [
                        {
                            "field": "assignee",
                            "from": "chenxing",
                            "fromString": "陈兴",
                            "to": "dev_a",
                            "toString": "开发A",
                        }
                    ],
                },
            ]
        },
    }

    timeline = extract_timeline(
        issue,
        role_settings={
            "dev_manager_roles": ["chenxing", "陈兴"],
        },
        teams=[
            {
                "id": "algo",
                "name": "算法组",
                "members": ["dev_a", "开发A"],
            }
        ],
    )

    assert timeline["dev_manager_assigned_at"] == "2026-02-05T09:00:00.000+00:00"
    assert timeline["dev_manager_assigned_from"] == "陈兴"
    assert timeline["dev_manager_assigned_to"] == "开发A"


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


def test_normalize_issue_extracts_assignee_transfer_events():
    issue = {
        "key": "ABC-301",
        "fields": {
            "summary": "transfer",
            "status": {"name": "In Progress"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "外部A", "name": "external_a"},
            "issuetype": {"name": "Task"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-03T00:00:00+00:00",
                    "items": [
                        {
                            "field": "assignee",
                            "from": "dev_a",
                            "fromString": "开发A",
                            "to": "external_a",
                            "toString": "外部A",
                        }
                    ],
                }
            ]
        },
    }

    card = normalize_issue(issue, base_url="https://jira.example.com")
    events = card["assignee_transfer_events"]
    assert len(events) == 1
    assert events[0]["from_login"] == "dev_a"
    assert events[0]["to_login"] == "external_a"
    assert card["assignee_login"] == "external_a"


def test_normalize_issue_quality_owner_falls_back_to_last_non_quality_assignee():
    issue = {
        "key": "ABC-302",
        "fields": {
            "summary": "qa resolved",
            "status": {"name": "Done"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "品质A", "name": "qa_a"},
            "issuetype": {"name": "Task"},
            "created": "2026-02-01T00:00:00+00:00",
        },
        "changelog": {
            "histories": [
                {
                    "created": "2026-02-03T00:00:00+00:00",
                    "items": [{"field": "assignee", "from": "dev_a", "fromString": "开发A", "to": "qa_a", "toString": "品质A"}],
                }
            ]
        },
    }

    card = normalize_issue(
        issue,
        base_url="https://jira.example.com",
        role_settings={
            "quality_roles": ["qa_a", "品质A"],
        },
    )
    assert card["assignee"] == "品质A"
    assert card["metric_owner"] == "开发A"


def test_parse_datetime_supports_jira_timezone_format_without_colon():
    point = parse_datetime("2026-02-24T13:38:14.000+0800")
    assert point is not None
    assert point.isoformat() == "2026-02-24T13:38:14+08:00"
