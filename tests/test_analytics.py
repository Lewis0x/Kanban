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

    # -- verify enriched summary text contains issue details --
    text = result["manager_summary_text"]
    # overview line
    assert "分配到开发 2 个" in text
    assert "已解决 1 个" in text
    # resolved section: by status then owner (ABC-1 is Done)
    assert "【已解决问题 (1)】" in text
    assert "ABC-1" in text
    assert "【Done】（1）" in text
    assert "Alice (1)：" in text
    # unresolved section lists ABC-3
    assert "【未解决问题 (1)】" in text
    assert "ABC-3" in text
    # new issue section lists both ABC-1 and ABC-3
    assert "【新引入问题 (2)】" in text
    # reopened section
    assert "【重开事件" in text


def test_build_manager_summary_includes_closed_in_period_via_closed_at():
    """本周期仅 closed_at 落在窗口内（resolved_at 为空或在外）也应计入已解决并出现在总结正文。"""
    window = resolve_period_window("custom", "2026-02-24T00:00:00+00:00", "2026-02-26T00:00:00+00:00")
    cards = [
        {
            "key": "CL-1",
            "summary": "仅关闭落在本周期",
            "status": "已关闭",
            "assignee": "Bob",
            "metric_owner": "Bob",
            "url": "http://x/CL-1",
            "timeline": {
                "created_at": "2026-02-20T00:00:00+00:00",
                "dev_manager_assigned_at": "2026-02-24T08:00:00+00:00",
                "resolved_at": None,
                "closed_at": "2026-02-25T12:00:00+00:00",
                "reopened_events": [],
            },
        },
    ]
    result = build_manager_summary(cards, window)
    assert result["manager_summary_cards"]["resolved_total"] == 1
    assert result["manager_summary_cards"]["unresolved_total"] == 0
    assert "CL-1" in result["manager_summary_text"]
    assert "【已解决问题 (1)】" in result["manager_summary_text"]


def test_resolved_section_groups_by_status_then_owner():
    """本周期已解决：先按状态，再按负责人。"""
    window = resolve_period_window("custom", "2026-02-24T00:00:00+00:00", "2026-02-26T00:00:00+00:00")
    cards = [
        {
            "key": "A-1",
            "summary": "done-a",
            "status": "Done",
            "assignee": "Alice",
            "metric_owner": "Alice",
            "timeline": {
                "dev_manager_assigned_at": "2026-02-24T01:00:00+00:00",
                "resolved_at": "2026-02-25T08:00:00+00:00",
            },
        },
        {
            "key": "B-1",
            "summary": "closed-b",
            "status": "Closed",
            "assignee": "Bob",
            "metric_owner": "Bob",
            "timeline": {
                "dev_manager_assigned_at": "2026-02-24T02:00:00+00:00",
                "resolved_at": "2026-02-25T09:00:00+00:00",
            },
        },
        {
            "key": "A-2",
            "summary": "done-a2",
            "status": "Done",
            "assignee": "Alice",
            "metric_owner": "Alice",
            "timeline": {
                "dev_manager_assigned_at": "2026-02-24T03:00:00+00:00",
                "resolved_at": "2026-02-25T10:00:00+00:00",
            },
        },
    ]
    result = build_manager_summary(cards, window)
    text = result["manager_summary_text"]
    assert result["manager_summary_cards"]["resolved_total"] == 3
    assert "【已解决问题 (3)】" in text
    # 状态按字母序：Closed 在 Done 前
    idx_closed = text.index("【Closed】")
    idx_done = text.index("【Done】")
    assert idx_closed < idx_done
    assert "Bob (1)：" in text
    assert "Alice (2)：" in text


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
