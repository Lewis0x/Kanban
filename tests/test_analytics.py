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
                "dev_manager_assigned_at": "2026-02-24T07:00:00+00:00",
                "developer_started_at": "2026-02-24T08:00:00+00:00",
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
                "dev_manager_assigned_at": "2026-01-01T07:00:00+00:00",
                "developer_started_at": "2026-01-01T08:00:00+00:00",
                "resolved_at": None,
                "reopened_events": [],
            }
        },
        {
            "key": "ABC-3",
            "summary": "three",
            "status": "In Progress",
            "assignee": "Alice",
            "metric_owner": "Alice",
            "url": "http://x/ABC-3",
            "timeline": {
                "created_at": "2026-02-24T02:00:00+00:00",
                "dev_manager_assigned_at": "2026-02-24T08:30:00+00:00",
                "developer_started_at": "2026-02-24T09:00:00+00:00",
                "resolved_at": None,
                "reopened_events": [],
            }
        },
    ]

    window = resolve_period_window("custom", "2026-02-24T00:00:00+00:00", "2026-02-26T00:00:00+00:00")
    result = build_manager_summary(cards, window)

    # ABC-1 and ABC-3 dev_manager_assigned_at in window; ABC-2 is outside
    assert result["manager_summary_cards"]["assigned_total"] == 2
    assert result["manager_summary_cards"]["resolved_total"] == 1
    assert result["manager_summary_cards"]["reopened_event_total"] == 1
    # ABC-1 and ABC-3 created in window
    assert result["manager_summary_cards"]["new_issue_total"] == 2
    # Only ABC-3 assigned in window AND is unresolved;
    # ABC-2 is unresolved but assigned outside window so not counted
    assert result["manager_summary_cards"]["unresolved_total"] == 1
    # net_change = new_issue_count - resolved_total = 2 - 1 = 1
    assert result["manager_summary_cards"]["net_change"] == 1
    assert result["period_focus"]["new_issue"]["enabled"] is True
    assert len(result["period_focus"]["reopened"]["items"]) == 1
    assert len(result["period_focus"]["new_issue"]["items"]) == 2


def test_resolved_total_uses_last_resolution_time():
    """Issue resolved twice: first outside window, last inside window."""
    cards = [
        {
            "key": "X-1",
            "summary": "multi-resolve",
            "status": "Done",
            "assignee": "Alice",
            "metric_owner": "Alice",
            "url": "http://x/X-1",
            "timeline": {
                "created_at": "2026-02-20T01:00:00+00:00",
                "dev_manager_assigned_at": "2026-02-20T02:00:00+00:00",
                "developer_started_at": "2026-02-20T03:00:00+00:00",
                # Last resolved_at (after reopen + re-resolve) falls in window
                "resolved_at": "2026-02-25T10:00:00+00:00",
                "reopened_events": ["2026-02-22T08:00:00+00:00"],
            }
        },
    ]

    window = resolve_period_window("custom", "2026-02-24T00:00:00+00:00", "2026-02-26T00:00:00+00:00")
    result = build_manager_summary(cards, window)

    # resolved_at is the LAST resolution time, which is inside the window
    assert result["manager_summary_cards"]["resolved_total"] == 1
