from app.metrics import build_gantt_rows, compute_member_metrics


def test_compute_member_metrics_basic():
    cards = [
        {
            "assignee": "Alice",
            "column": "Done",
            "priority": "High",
            "timeline": {
                "created_at": "2026-02-01T00:00:00+00:00",
                "resolved_at": "2026-02-02T00:00:00+00:00",
            },
        },
        {
            "assignee": "Alice",
            "column": "审核中",
            "priority": "Low",
            "timeline": {
                "created_at": "2026-02-01T00:00:00+00:00",
                "resolved_at": None,
            },
        },
    ]
    rows = compute_member_metrics(cards)
    assert len(rows) == 1
    assert rows[0]["assignee"] == "Alice"
    assert rows[0]["resolved"] == 1
    assert rows[0]["wip"] == 1


def test_build_gantt_rows_member_mode():
    cards = [
        {
            "assignee": "Alice",
            "metric_owner": "开发A",
            "sprint": "Sprint 11",
            "key": "ABC-1",
            "summary": "Fix",
            "priority": "High",
            "status": "Done",
            "url": "http://x",
            "timeline": {
                "created_at": "2026-02-01T00:00:00+00:00",
                "developer_started_at": "2026-02-01T08:00:00+00:00",
                "resolved_at": "2026-02-02T00:00:00+00:00",
                "closed_at": None,
            },
        }
    ]
    rows = build_gantt_rows(cards, mode="member")
    assert rows[0]["lane"] == "开发A"
    assert rows[0]["start"] == "2026-02-01T08:00:00+00:00"


def test_build_gantt_rows_skips_issue_without_in_progress_start():
    cards = [
        {
            "assignee": "Alice",
            "metric_owner": "开发A",
            "sprint": "Sprint 11",
            "key": "ABC-2",
            "summary": "Fix2",
            "priority": "High",
            "status": "Done",
            "url": "http://x",
            "timeline": {
                "created_at": "2026-02-01T00:00:00+00:00",
                "developer_started_at": None,
                "resolved_at": "2026-02-02T00:00:00+00:00",
                "closed_at": None,
            },
        }
    ]

    rows = build_gantt_rows(cards, mode="member")
    assert rows == []


def test_build_gantt_rows_skips_issue_without_resolved_end():
    cards = [
        {
            "assignee": "Alice",
            "metric_owner": "开发A",
            "sprint": "Sprint 11",
            "key": "ABC-3",
            "summary": "Fix3",
            "priority": "High",
            "status": "In Progress",
            "url": "http://x",
            "timeline": {
                "created_at": "2026-02-01T00:00:00+00:00",
                "developer_started_at": "2026-02-01T08:00:00+00:00",
                "resolved_at": None,
                "closed_at": None,
            },
        }
    ]

    rows = build_gantt_rows(cards, mode="member")
    assert rows == []


def test_compute_member_metrics_uses_metric_owner_when_present():
    cards = [
        {
            "assignee": "产品经理",
            "metric_owner": "开发A",
            "column": "Done",
            "priority": "High",
            "timeline": {
                "created_at": "2026-02-01T00:00:00+00:00",
                "resolved_at": "2026-02-02T00:00:00+00:00",
            },
        }
    ]

    rows = compute_member_metrics(cards)
    assert len(rows) == 1
    assert rows[0]["assignee"] == "开发A"
    assert rows[0]["resolved"] == 1


def test_compute_member_metrics_excludes_quality_roles():
    cards = [
        {
            "assignee": "李启沆",
            "metric_owner": "李启沆",
            "column": "审核中",
            "priority": "High",
            "timeline": {
                "created_at": "2026-02-01T00:00:00+00:00",
                "resolved_at": None,
            },
        },
        {
            "assignee": "开发A",
            "metric_owner": "开发A",
            "column": "Done",
            "priority": "Medium",
            "timeline": {
                "created_at": "2026-02-01T00:00:00+00:00",
                "resolved_at": "2026-02-03T00:00:00+00:00",
            },
        },
    ]

    rows = compute_member_metrics(cards, exclude_roles={"李启沆"})
    assert len(rows) == 1
    assert rows[0]["assignee"] == "开发A"


def test_compute_member_metrics_no_exclusion_by_default():
    cards = [
        {
            "assignee": "李启沆",
            "metric_owner": "李启沆",
            "column": "审核中",
            "priority": "High",
            "timeline": {
                "created_at": "2026-02-01T00:00:00+00:00",
                "resolved_at": None,
            },
        },
    ]

    rows = compute_member_metrics(cards)
    assert len(rows) == 1
    assert rows[0]["assignee"] == "李启沆"
