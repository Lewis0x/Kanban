from __future__ import annotations

from typing import Any

from .normalize import parse_datetime


def _in_window(value: str | None, window: dict[str, Any]) -> bool:
    point = parse_datetime(value)
    if not point:
        return False
    start = window["start"]
    end = window["end"]
    return start <= point < end


def _count_reopened_events(card: dict[str, Any], window: dict[str, Any]) -> int:
    timeline = card.get("timeline", {}) or {}
    events = timeline.get("reopened_events", []) or []
    return sum(1 for event_at in events if _in_window(event_at, window))


def _windowed_reopen_events(card: dict[str, Any], window: dict[str, Any]) -> list[str]:
    timeline = card.get("timeline", {}) or {}
    events = timeline.get("reopened_events", []) or []
    return [event_at for event_at in events if _in_window(event_at, window)]


def build_manager_summary(cards: list[dict[str, Any]], window: dict[str, Any]) -> dict[str, Any]:
    assigned_total = sum(1 for card in cards if _in_window(card.get("timeline", {}).get("dev_manager_assigned_at"), window))
    resolved_total = sum(1 for card in cards if _in_window(card.get("timeline", {}).get("resolved_at"), window))
    reopened_events = sum(_count_reopened_events(card, window) for card in cards)
    new_issue_count = sum(1 for card in cards if _in_window(card.get("timeline", {}).get("created_at"), window))

    unresolved_total = sum(
        1 for card in cards
        if _in_window(card.get("timeline", {}).get("dev_manager_assigned_at"), window)
        and not card.get("timeline", {}).get("resolved_at")
    )
    resolution_rate = round((resolved_total / assigned_total) * 100, 2) if assigned_total else 0.0
    net_change = new_issue_count - resolved_total

    summary_cards = {
        "assigned_total": assigned_total,
        "resolved_total": resolved_total,
        "unresolved_total": unresolved_total,
        "reopened_event_total": reopened_events,
        "new_issue_total": new_issue_count,
        "resolution_rate": resolution_rate,
        "net_change": net_change,
    }

    summary_text = (
        f"{window['label']}：分配到开发 {assigned_total} 个，已解决 {resolved_total} 个，"
        f"未解决 {unresolved_total} 个，重开事件 {reopened_events} 次，"
        f"新引入问题 {new_issue_count} 个，净变化 {net_change:+d} 个。"
    )

    reopened_items: list[dict[str, Any]] = []
    new_issue_items: list[dict[str, Any]] = []
    for card in cards:
        timeline = card.get("timeline", {}) or {}

        reopen_events = _windowed_reopen_events(card, window)
        if reopen_events:
            reopened_items.append(
                {
                    "key": card.get("key"),
                    "summary": card.get("summary"),
                    "status": card.get("status"),
                    "assignee": card.get("assignee"),
                    "metric_owner": card.get("metric_owner"),
                    "reopen_count": len(reopen_events),
                    "last_reopened_at": reopen_events[-1],
                    "url": card.get("url"),
                }
            )

        if _in_window(timeline.get("created_at"), window):
            new_issue_items.append(
                {
                    "key": card.get("key"),
                    "summary": card.get("summary"),
                    "status": card.get("status"),
                    "assignee": card.get("assignee"),
                    "metric_owner": card.get("metric_owner"),
                    "created_at": timeline.get("created_at"),
                    "url": card.get("url"),
                }
            )

    reopened_items.sort(key=lambda row: row.get("last_reopened_at") or "", reverse=True)
    new_issue_items.sort(key=lambda row: row.get("created_at") or "", reverse=True)

    period_focus = {
        "reopened": {
            "event_count": reopened_events,
            "issue_count": len(reopened_items),
            "items": reopened_items,
        },
        "new_issue": {
            "enabled": True,
            "count": new_issue_count,
            "items": new_issue_items,
            "note": "当前按创建时间口径统计；后续可切换为自定义字段口径",
        },
    }

    return {
        "summary_window": {
            "mode": window["mode"],
            "label": window["label"],
            "start": window["start"].isoformat(),
            "end": window["end"].isoformat(),
            "timezone": window["timezone"],
        },
        "manager_summary_cards": summary_cards,
        "manager_summary_text": summary_text,
        "period_focus": period_focus,
    }
