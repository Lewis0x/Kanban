from __future__ import annotations

from app.cache_summary import build_summary_payload, format_text_report, summarize_by_metric_owner


def test_summarize_by_metric_owner_orders_and_unassigned():
    cards = [
        {"key": "B-2", "metric_owner": "张三", "summary": "b"},
        {"key": "A-1", "metric_owner": "张三", "summary": "a"},
        {"key": "C-3", "metric_owner": "", "summary": "c"},
        {"key": "D-4", "metric_owner": "李四", "summary": "d"},
    ]
    s = summarize_by_metric_owner(cards)
    assert s["total_issues"] == 4
    assert s["owner_counts"]["张三"] == 2
    assert s["owner_counts"]["李四"] == 1
    assert s["owner_counts"]["未分配"] == 1
    assert [c["key"] for c in s["by_owner"]["张三"]] == ["A-1", "B-2"]


def test_build_summary_payload_and_text():
    cards = [
        {
            "key": "X-1",
            "summary": "hello",
            "status": "Open",
            "column": "To Do",
            "assignee": "经办",
            "task_owner": "负责人",
            "task_owner_source": "jira_field",
            "task_owner_jira_field": "customfield_999",
            "metric_owner": "负责人",
            "priority": "High",
            "issue_type": "任务",
            "url": "https://jira.example/browse/X-1",
        }
    ]
    p = build_summary_payload(cards, meta={"jql_preview": "project = X"})
    assert p["total_issues"] == 1
    assert "负责人" in p["by_owner"]
    row0 = p["by_owner"]["负责人"][0]
    assert row0["task_owner_source"] == "jira_field"
    assert "customfield_999" in row0["task_owner_provenance"]
    text = format_text_report(p)
    assert "X-1" in text
    assert "负责人" in text
    assert "project = X" in text
    assert "Jira自定义字段" in text
