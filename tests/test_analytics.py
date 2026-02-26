from app.analytics import build_manager_summary
from app.period import resolve_period_window


def test_build_manager_summary_counts_window_metrics():
    cards = [
        {
            "key": "ABC-1",
            "summary": "one",
            "status": "Done",
            "assignee": "Alice",
            "metric_owner": "Alice",
            "url": "http://x/ABC-1",
            "timeline": {
                "created_at": "2026-02-24T01:00:00+00:00",
                    "dev_manager_assigned_at": "2026-02-24T08:00:00+00:00",
                "resolved_at": "2026-02-25T08:00:00+00:00",
                "reopened_events": ["2026-02-25T10:00:00+00:00", "2026-02-26T10:00:00+00:00"],
            }
        },
        {
            "key": "ABC-2",
            "summary": "two",
            "status": "In Progress",
            "assignee": "Bob",
            "metric_owner": "Bob",
            "url": "http://x/ABC-2",
            "timeline": {
                "created_at": "2026-01-01T00:00:00+00:00",
                    "dev_manager_assigned_at": "2026-01-01T08:00:00+00:00",
                "resolved_at": None,
                "reopened_events": [],
            }
        },
    ]

    window = resolve_period_window("custom", "2026-02-24T00:00:00+00:00", "2026-02-26T00:00:00+00:00")
    result = build_manager_summary(cards, window)

    assert result["manager_summary_cards"]["assigned_total"] == 1
    assert result["manager_summary_cards"]["resolved_total"] == 1
    assert result["manager_summary_cards"]["reopened_event_total"] == 1
    assert result["manager_summary_cards"]["new_issue_total"] == 1
    assert result["manager_summary_cards"]["unresolved_total"] == 1
    assert result["manager_summary_issue_keys"]["assigned"] == ["ABC-1"]
    assert result["manager_summary_issue_keys"]["resolved"] == ["ABC-1"]
    assert result["manager_summary_issue_keys"]["unresolved"] == ["ABC-2"]
    assert result["manager_summary_issue_keys"]["new_issue"] == ["ABC-1"]
    assert result["manager_summary_issue_keys"]["reopened"] == ["ABC-1"]
    assert result["period_focus"]["new_issue"]["enabled"] is True
    assert len(result["period_focus"]["reopened"]["items"]) == 1
    assert len(result["period_focus"]["new_issue"]["items"]) == 1


def test_build_manager_summary_counts_transfer_out_and_excludes_returned_issue():
    cards = [
        {
            "key": "ABC-10",
            "summary": "out and stay out",
            "status": "In Progress",
            "assignee": "外部A",
            "assignee_login": "external_a",
            "metric_owner": "开发A",
            "url": "http://x/ABC-10",
            "timeline": {
                "created_at": "2026-02-24T01:00:00+00:00",
                "developer_started_at": "2026-02-24T08:00:00+00:00",
                "resolved_at": None,
                "reopened_events": [],
            },
            "assignee_transfer_events": [
                {
                    "at": "2026-02-24T12:00:00+00:00",
                    "from_login": "dev_a",
                    "from_display": "开发A",
                    "to_login": "external_a",
                    "to_display": "外部A",
                }
            ],
        },
        {
            "key": "ABC-11",
            "summary": "out then back",
            "status": "In Progress",
            "assignee": "开发A",
            "assignee_login": "dev_a",
            "metric_owner": "开发A",
            "url": "http://x/ABC-11",
            "timeline": {
                "created_at": "2026-02-24T01:00:00+00:00",
                "developer_started_at": "2026-02-24T08:00:00+00:00",
                "resolved_at": None,
                "reopened_events": [],
            },
            "assignee_transfer_events": [
                {
                    "at": "2026-02-24T10:00:00+00:00",
                    "from_login": "dev_a",
                    "from_display": "开发A",
                    "to_login": "external_b",
                    "to_display": "外部B",
                },
                {
                    "at": "2026-02-24T18:00:00+00:00",
                    "from_login": "external_b",
                    "from_display": "外部B",
                    "to_login": "dev_a",
                    "to_display": "开发A",
                },
            ],
        },
    ]

    window = resolve_period_window("custom", "2026-02-24T00:00:00+00:00", "2026-02-25T00:00:00+00:00")
    result = build_manager_summary(
        cards,
        window,
        teams=[
            {
                "id": "team_a",
                "name": "团队A",
                "owner": "leader_a",
                "members": ["dev_a"],
            }
        ],
    )

    assert result["manager_summary_cards"]["transfer_out_event_total"] == 2
    assert result["manager_summary_cards"]["transfer_out_issue_total"] == 1
    transfer_out = result["period_focus"]["transfer_out"]
    assert transfer_out["event_count"] == 2
    assert transfer_out["issue_count"] == 1
    assert len(transfer_out["teams"]) == 1
    assert transfer_out["teams"][0]["transfer_out_issue_count"] == 1
    assert transfer_out["teams"][0]["transfer_out_event_count"] == 2
    assert transfer_out["teams"][0]["items"][0]["key"] == "ABC-10"
    assert result["manager_summary_issue_keys"]["transfer_out"] == ["ABC-10"]


def test_build_manager_summary_includes_team_period_summary_and_other_last():
    cards = [
        {
            "key": "ABC-20",
            "summary": "team member issue",
            "status": "Done",
            "assignee": "开发A",
            "assignee_login": "dev_a",
            "metric_owner": "开发A",
            "url": "http://x/ABC-20",
            "timeline": {
                "created_at": "2026-02-24T01:00:00+00:00",
                "developer_started_at": "2026-02-24T08:00:00+00:00",
                "resolved_at": "2026-02-24T18:00:00+00:00",
                "reopened_events": [],
            },
            "assignee_transfer_events": [],
        },
        {
            "key": "ABC-21",
            "summary": "external issue",
            "status": "In Progress",
            "assignee": "外部A",
            "assignee_login": "external_a",
            "metric_owner": "外部A",
            "url": "http://x/ABC-21",
            "timeline": {
                "created_at": "2026-02-24T01:00:00+00:00",
                "developer_started_at": "2026-02-24T08:00:00+00:00",
                "resolved_at": None,
                "reopened_events": [],
            },
            "assignee_transfer_events": [],
        },
    ]

    window = resolve_period_window("custom", "2026-02-24T00:00:00+00:00", "2026-02-25T00:00:00+00:00")
    result = build_manager_summary(
        cards,
        window,
        teams=[
            {
                "id": "team_a",
                "name": "团队A",
                "owner": "leader_a",
                "members": ["dev_a"],
            }
        ],
    )

    team_rows = result["team_period_summary"]
    assert len(team_rows) == 2
    assert team_rows[0]["team_name"] == "团队A"
    assert team_rows[0]["resolved_total"] == 1
    assert team_rows[0]["issue_keys"] == ["ABC-20"]
    assert team_rows[-1]["team_name"] == "其他团队"
    assert team_rows[-1]["issue_keys"] == ["ABC-21"]
    assert "团队概览" in result["manager_summary_text"]
    assert "ABC-20" in result["manager_summary_text"]


def test_build_manager_summary_assigned_uses_dev_manager_assignment():
    cards = [
        {
            "key": "ABC-30",
            "summary": "fallback assign time",
            "status": "In Progress",
            "assignee": "开发A",
            "assignee_login": "dev_a",
            "metric_owner": "开发A",
            "url": "http://x/ABC-30",
            "timeline": {
                "created_at": "2026-02-24T01:00:00+00:00",
                    "dev_manager_assigned_at": "2026-02-24T08:00:00+00:00",
                "resolved_at": None,
                "reopened_events": [],
            },
            "assignee_transfer_events": [],
        }
    ]

    window = resolve_period_window("custom", "2026-02-24T00:00:00+00:00", "2026-02-25T00:00:00+00:00")
    result = build_manager_summary(cards, window)
    assert result["manager_summary_cards"]["assigned_total"] == 1


def test_build_manager_summary_assigned_uses_assignee_transfer_fallback():
    cards = [
        {
            "key": "ZWCAD-44076",
            "summary": "assigned by assignee transfer",
            "status": "正在解决",
            "assignee": "张剑锋",
            "assignee_login": "zhangjianfeng",
            "metric_owner": "张剑锋",
            "url": "http://x/ZWCAD-44076",
            "timeline": {
                "created_at": "2025-10-09T11:41:36.000+0800",
                "developer_started_at": None,
                "in_progress_at": None,
                "resolved_at": None,
                "reopened_events": [],
            },
            "assignee_transfer_events": [
                {
                    "at": "2026-02-24T13:38:14.000+0800",
                    "from_login": "chenxing",
                    "from_display": "陈兴",
                    "to_login": "zhangjianfeng",
                    "to_display": "张剑锋",
                }
            ],
        }
    ]

    window = resolve_period_window("custom", "2026-02-24T00:00:00+08:00", "2026-02-25T00:00:00+08:00")
    result = build_manager_summary(cards, window)
    assert result["manager_summary_cards"]["assigned_total"] == 1
