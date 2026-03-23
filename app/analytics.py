from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .normalize import parse_datetime

_SUMMARY_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "config" / "manager_summary_template.yaml"

# 与 config/manager_summary_template.yaml 默认内容一致；文件缺失或缺键时回退
_BUILTIN_SUMMARY_STRINGS: dict[str, str] = {
    "overview": (
        "{label}：分配到开发 {assigned_total} 个，已解决 {resolved_total} 个，"
        "未解决 {unresolved_total} 个，重开事件 {reopened_events} 次，"
        "新引入问题 {new_issue_total} 个，净变化 {net_change} 个。"
    ),
    "section_resolved": "【已解决问题 ({resolved_total})】",
    "section_unresolved": "【未解决问题 ({unresolved_total})】",
    "section_reopened": "【重开事件 ({reopened_events} 次，涉及 {reopened_issue_count} 个问题)】",
    "section_new_issue": "【新引入问题 ({new_issue_total})】",
    "owner_group": "  {owner} ({count})：",
    # 已解决：先按状态，再按负责人（缩进多一级）
    "resolved_status_group": "  【{status}】（{count}）",
    "resolved_owner_group": "    {owner} ({count})：",
    "item_resolved": "      - {key}  {summary}",
    "item_unresolved": "    - {key}  {summary}  [{status}]",
    "item_reopened": "  - {key}  {summary}  重开{reopen_count}次  [{owner}]",
    "item_new_issue": "  - {key}  {summary}  [{status}]  [{owner}]",
}


def _brace_escape(text: str) -> str:
    """避免 Jira 摘要等含 {{ / }} 破坏 str.format。"""
    return text.replace("{", "{{").replace("}", "}}")


def _fmt(template: str, **kwargs: Any) -> str:
    safe: dict[str, Any] = {}
    for key, value in kwargs.items():
        if isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, (int, float)):
            safe[key] = value
        elif value is None:
            safe[key] = ""
        else:
            safe[key] = _brace_escape(str(value))
    return template.format(**safe)


def load_manager_summary_strings() -> dict[str, str]:
    """加载周期总结文本模板；优先 config/manager_summary_template.yaml，缺键回退内置。"""
    merged = dict(_BUILTIN_SUMMARY_STRINGS)
    path = _SUMMARY_TEMPLATE_PATH
    if path.exists():
        with path.open("r", encoding="utf-8") as file:
            raw = yaml.safe_load(file) or {}
        user_strings = raw.get("strings") or {}
        if isinstance(user_strings, dict):
            for key, value in user_strings.items():
                if isinstance(value, str) and value.strip():
                    merged[str(key)] = value
    return merged


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


def _owner_of(card: dict[str, Any]) -> str:
    return card.get("metric_owner") or card.get("assignee") or "未分配"


def _group_by_owner(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group a list of card-like dicts by metric_owner, preserving insertion order."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        owner = _owner_of(item)
        groups.setdefault(owner, []).append(item)
    return groups


def _group_by_status(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group cards by Jira status; empty/missing status → 「（无状态）」."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        raw = (item.get("status") or "").strip()
        label = raw if raw else "（无状态）"
        groups.setdefault(label, []).append(item)
    return groups


def _sort_status_keys(statuses: list[str]) -> list[str]:
    """字母序；「（无状态）」排在最后。"""
    return sorted(statuses, key=lambda s: (s == "（无状态）", s.lower()))


def _has_terminal_resolution(timeline: dict[str, Any]) -> bool:
    """是否已有解决/关闭时间（用于未解决列表排除已终态问题）。"""
    return bool((timeline or {}).get("resolved_at") or (timeline or {}).get("closed_at"))


def build_manager_summary(cards: list[dict[str, Any]], window: dict[str, Any]) -> dict[str, Any]:
    # -- classify cards into resolved / unresolved / reopened / new_issue --
    resolved_cards: list[dict[str, Any]] = []
    unresolved_cards: list[dict[str, Any]] = []
    reopened_items: list[dict[str, Any]] = []
    new_issue_items: list[dict[str, Any]] = []

    for card in cards:
        timeline = card.get("timeline", {}) or {}

        is_assigned = _in_window(timeline.get("dev_manager_assigned_at"), window)
        # 本周期「已解决」：解决时间或关闭时间在窗口内（含仅走到「已关闭」分步工作流）
        is_resolved = _in_window(timeline.get("resolved_at"), window) or _in_window(
            timeline.get("closed_at"), window
        )

        if is_resolved:
            resolved_cards.append(card)
        if is_assigned and not _has_terminal_resolution(timeline):
            unresolved_cards.append(card)

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

    assigned_total = sum(1 for card in cards if _in_window(card.get("timeline", {}).get("dev_manager_assigned_at"), window))
    resolved_total = len(resolved_cards)
    unresolved_total = len(unresolved_cards)
    reopened_events = sum(_count_reopened_events(card, window) for card in cards)
    new_issue_count = len(new_issue_items)
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

    tmpl = load_manager_summary_strings()

    # -- build detailed multi-line summary text --
    lines: list[str] = []

    # 1. overview line
    lines.append(
        _fmt(
            tmpl["overview"],
            label=window["label"],
            assigned_total=assigned_total,
            resolved_total=resolved_total,
            unresolved_total=unresolved_total,
            reopened_events=reopened_events,
            new_issue_total=new_issue_count,
            net_change=f"{net_change:+d}",
        )
    )

    # 2. resolved issues: by status, then by owner
    if resolved_cards:
        lines.append("")
        lines.append(_fmt(tmpl["section_resolved"], resolved_total=resolved_total))
        resolved_by_status = _group_by_status(resolved_cards)
        status_tmpl = tmpl.get("resolved_status_group", _BUILTIN_SUMMARY_STRINGS["resolved_status_group"])
        owner_tmpl = tmpl.get("resolved_owner_group", _BUILTIN_SUMMARY_STRINGS["resolved_owner_group"])
        item_tmpl = tmpl.get("item_resolved", _BUILTIN_SUMMARY_STRINGS["item_resolved"])
        for status in _sort_status_keys(list(resolved_by_status.keys())):
            in_status = resolved_by_status[status]
            lines.append(_fmt(status_tmpl, status=status, count=len(in_status)))
            for owner, items in _group_by_owner(in_status).items():
                lines.append(_fmt(owner_tmpl, owner=owner, count=len(items)))
                for c in items:
                    lines.append(
                        _fmt(
                            item_tmpl,
                            key=c.get("key", "?"),
                            summary=c.get("summary", ""),
                        )
                    )

    # 3. unresolved issues grouped by owner
    if unresolved_cards:
        lines.append("")
        lines.append(_fmt(tmpl["section_unresolved"], unresolved_total=unresolved_total))
        unresolved_by_owner = _group_by_owner(unresolved_cards)
        for owner, items in unresolved_by_owner.items():
            lines.append(_fmt(tmpl["owner_group"], owner=owner, count=len(items)))
            for c in items:
                lines.append(
                    _fmt(
                        tmpl["item_unresolved"],
                        key=c.get("key", "?"),
                        summary=c.get("summary", ""),
                        status=c.get("status", ""),
                    )
                )

    # 4. reopened issues
    if reopened_items:
        lines.append("")
        lines.append(
            _fmt(
                tmpl["section_reopened"],
                reopened_events=reopened_events,
                reopened_issue_count=len(reopened_items),
            )
        )
        for item in reopened_items:
            owner = _owner_of(item)
            lines.append(
                _fmt(
                    tmpl["item_reopened"],
                    key=item.get("key", "?"),
                    summary=item.get("summary", ""),
                    reopen_count=item.get("reopen_count", 0),
                    owner=owner,
                )
            )

    # 5. new issues
    if new_issue_items:
        lines.append("")
        lines.append(_fmt(tmpl["section_new_issue"], new_issue_total=new_issue_count))
        for item in new_issue_items:
            owner = _owner_of(item)
            lines.append(
                _fmt(
                    tmpl["item_new_issue"],
                    key=item.get("key", "?"),
                    summary=item.get("summary", ""),
                    status=item.get("status", ""),
                    owner=owner,
                )
            )

    summary_text = "\n".join(lines)

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
