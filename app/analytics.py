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


def resolve_assigned_marker(card: dict[str, Any]) -> dict[str, str | None]:
    timeline = card.get("timeline", {}) or {}
    direct = timeline.get("dev_manager_assigned_at")
    if direct:
        return {"at": direct, "source": "dev_manager_assigned_at"}

    owner_candidates = {
        _normalize_identity(card.get("metric_owner")),
        _normalize_identity(card.get("assignee_login")),
        _normalize_identity(card.get("assignee")),
    }
    events = card.get("assignee_transfer_events") or []
    sorted_events = sorted(events, key=lambda row: row.get("at") or "", reverse=True)
    for event in sorted_events:
        to_login = _normalize_identity(event.get("to_login"))
        to_display = _normalize_identity(event.get("to_display"))
        if (to_login and to_login in owner_candidates) or (to_display and to_display in owner_candidates):
            assigned_at = event.get("at")
            if assigned_at:
                return {"at": assigned_at, "source": "assignee_transfer"}

    return {"at": None, "source": None}


def _assigned_at(card: dict[str, Any]) -> str | None:
    return resolve_assigned_marker(card).get("at")


def build_assignment_debug(cards: list[dict[str, Any]], window: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for card in cards:
        marker = resolve_assigned_marker(card)
        assigned_at = marker.get("at")
        rows.append(
            {
                "key": card.get("key"),
                "assignee": card.get("assignee"),
                "metric_owner": card.get("metric_owner"),
                "assigned_at": assigned_at,
                "assigned_source": marker.get("source"),
                "in_window": _in_window(assigned_at, window),
            }
        )

    rows.sort(key=lambda row: str(row.get("assigned_at") or ""), reverse=True)
    return {
        "window": {
            "mode": window["mode"],
            "label": window["label"],
            "start": window["start"].isoformat(),
            "end": window["end"].isoformat(),
            "timezone": window["timezone"],
        },
        "rows": rows,
    }


def _normalize_identity(value: str | None) -> str:
    return (value or "").strip().lower()


def _build_team_membership(teams: list[dict[str, Any]]) -> dict[str, set[str]]:
    membership: dict[str, set[str]] = {}
    for team in teams:
        team_id = str(team.get("id") or "").strip()
        if not team_id:
            continue
        members = team.get("members") or []
        membership[team_id] = {_normalize_identity(str(member)) for member in members if str(member).strip()}
    return membership


def _classify_card_team(card: dict[str, Any], teams: list[dict[str, Any]], membership: dict[str, set[str]]) -> tuple[str, str]:
    identities = {
        _normalize_identity(card.get("metric_owner")),
        _normalize_identity(card.get("assignee_login")),
        _normalize_identity(card.get("assignee")),
    }

    for team in teams:
        team_id = str(team.get("id") or "").strip()
        if not team_id:
            continue
        members = membership.get(team_id, set())
        if any(identity and identity in members for identity in identities):
            return team_id, str(team.get("name") or team_id)

    return "other", "其他团队"


def _build_team_period_summary(cards: list[dict[str, Any]], window: dict[str, Any], teams: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not cards:
        return []

    membership = _build_team_membership(teams)
    grouped: dict[str, dict[str, Any]] = {}

    for card in cards:
        team_id, team_name = _classify_card_team(card, teams, membership)
        row = grouped.setdefault(
            team_id,
            {
                "team_id": team_id,
                "team_name": team_name,
                "total": 0,
                "assigned_total": 0,
                "resolved_total": 0,
                "unresolved_total": 0,
                "issue_keys": [],
            },
        )
        row["total"] += 1
        issue_key = str(card.get("key") or "").strip()
        if issue_key:
            row["issue_keys"].append(issue_key)
        timeline = card.get("timeline", {}) or {}
        if _in_window(_assigned_at(card), window):
            row["assigned_total"] += 1
        if _in_window(timeline.get("resolved_at"), window):
            row["resolved_total"] += 1
        if not timeline.get("resolved_at"):
            row["unresolved_total"] += 1

    rows = list(grouped.values())
    for row in rows:
        row["issue_keys"] = sorted(set(row.get("issue_keys") or []))
    rows.sort(key=lambda row: (row["team_name"] == "其他团队", str(row["team_name"])))
    return rows


def _resolve_event_user_identity(event: dict[str, Any], prefix: str) -> str:
    login = _normalize_identity(event.get(f"{prefix}_login"))
    if login:
        return login
    return _normalize_identity(event.get(f"{prefix}_display"))


def _resolve_current_identity(card: dict[str, Any]) -> str:
    login = _normalize_identity(card.get("assignee_login"))
    if login:
        return login
    return _normalize_identity(card.get("assignee"))


def _is_member(user_identity: str, team_members: set[str]) -> bool:
    return bool(user_identity and user_identity in team_members)


def _build_team_transfer_out_summary(
    cards: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    window: dict[str, Any],
) -> list[dict[str, Any]]:
    if not teams:
        return []

    membership = _build_team_membership(teams)
    summaries: list[dict[str, Any]] = []

    for team in teams:
        team_id = str(team.get("id") or "").strip()
        if not team_id:
            continue
        team_members = membership.get(team_id, set())

        event_count = 0
        transfer_issue_keys: set[str] = set()
        transfer_items: list[dict[str, Any]] = []

        for card in cards:
            events = card.get("assignee_transfer_events") or []
            if not events:
                continue

            sorted_events = sorted(events, key=lambda row: row.get("at") or "")
            out_events_in_window: list[dict[str, Any]] = []
            last_event_before_window_end: dict[str, Any] | None = None

            for event in sorted_events:
                changed_at = event.get("at")
                if not changed_at:
                    continue

                point = parse_datetime(changed_at)
                if not point:
                    continue
                if point < window["end"]:
                    last_event_before_window_end = event

                from_identity = _resolve_event_user_identity(event, "from")
                to_identity = _resolve_event_user_identity(event, "to")
                from_in_team = _is_member(from_identity, team_members)
                to_in_team = _is_member(to_identity, team_members)

                if window["start"] <= point < window["end"] and from_in_team and not to_in_team:
                    out_events_in_window.append(event)

            if not out_events_in_window:
                continue

            end_in_team = False
            if last_event_before_window_end is not None:
                end_identity = _resolve_event_user_identity(last_event_before_window_end, "to")
                end_in_team = _is_member(end_identity, team_members)
            else:
                end_in_team = _is_member(_resolve_current_identity(card), team_members)

            event_count += len(out_events_in_window)
            if end_in_team:
                continue

            transfer_issue_keys.add(str(card.get("key") or ""))
            latest_out = out_events_in_window[-1]
            transfer_items.append(
                {
                    "key": card.get("key"),
                    "summary": card.get("summary"),
                    "status": card.get("status"),
                    "assignee": card.get("assignee"),
                    "metric_owner": card.get("metric_owner"),
                    "latest_transfer_out_at": latest_out.get("at"),
                    "from": latest_out.get("from_display") or latest_out.get("from_login") or "-",
                    "to": latest_out.get("to_display") or latest_out.get("to_login") or "-",
                    "event_count": len(out_events_in_window),
                    "url": card.get("url"),
                }
            )

        transfer_items.sort(key=lambda row: row.get("latest_transfer_out_at") or "", reverse=True)
        summaries.append(
            {
                "team_id": team_id,
                "team_name": team.get("name") or team_id,
                "owner": team.get("owner") or "",
                "member_count": len(team_members),
                "transfer_out_issue_count": len([key for key in transfer_issue_keys if key]),
                "transfer_out_event_count": event_count,
                "items": transfer_items,
            }
        )

    return summaries


def build_manager_summary(cards: list[dict[str, Any]], window: dict[str, Any], teams: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    assigned_total = sum(1 for card in cards if _in_window(_assigned_at(card), window))
    resolved_total = sum(1 for card in cards if _in_window(card.get("timeline", {}).get("resolved_at"), window))
    reopened_events = sum(_count_reopened_events(card, window) for card in cards)
    new_issue_count = sum(1 for card in cards if _in_window(card.get("timeline", {}).get("created_at"), window))
    team_summary = _build_team_transfer_out_summary(cards, teams or [], window)
    team_period_summary = _build_team_period_summary(cards, window, teams or [])
    transfer_out_issue_total = sum(int(row.get("transfer_out_issue_count", 0)) for row in team_summary)
    transfer_out_event_total = sum(int(row.get("transfer_out_event_count", 0)) for row in team_summary)
    assigned_keys = sorted(
        {
            str(card.get("key") or "").strip()
            for card in cards
            if _in_window(_assigned_at(card), window) and str(card.get("key") or "").strip()
        }
    )
    resolved_keys = sorted(
        {
            str(card.get("key") or "").strip()
            for card in cards
            if _in_window(card.get("timeline", {}).get("resolved_at"), window) and str(card.get("key") or "").strip()
        }
    )
    unresolved_keys = sorted(
        {
            str(card.get("key") or "").strip()
            for card in cards
            if not card.get("timeline", {}).get("resolved_at") and str(card.get("key") or "").strip()
        }
    )
    reopened_keys = sorted(
        {
            str(card.get("key") or "").strip()
            for card in cards
            if _windowed_reopen_events(card, window) and str(card.get("key") or "").strip()
        }
    )
    new_issue_keys = sorted(
        {
            str(card.get("key") or "").strip()
            for card in cards
            if _in_window(card.get("timeline", {}).get("created_at"), window) and str(card.get("key") or "").strip()
        }
    )
    transfer_out_keys = sorted(
        {
            str(item.get("key") or "").strip()
            for team_row in team_summary
            for item in (team_row.get("items") or [])
            if str(item.get("key") or "").strip()
        }
    )

    unresolved_total = len([card for card in cards if not card.get("timeline", {}).get("resolved_at")])
    resolution_rate = round((resolved_total / assigned_total) * 100, 2) if assigned_total else 0.0
    net_change = assigned_total - resolved_total

    summary_cards = {
        "assigned_total": assigned_total,
        "resolved_total": resolved_total,
        "unresolved_total": unresolved_total,
        "reopened_event_total": reopened_events,
        "new_issue_total": new_issue_count,
        "transfer_out_issue_total": transfer_out_issue_total,
        "transfer_out_event_total": transfer_out_event_total,
        "resolution_rate": resolution_rate,
        "net_change": net_change,
    }
    summary_issue_keys = {
        "assigned": assigned_keys,
        "resolved": resolved_keys,
        "unresolved": unresolved_keys,
        "reopened": reopened_keys,
        "new_issue": new_issue_keys,
        "transfer_out": transfer_out_keys,
    }

    summary_text = (
        f"{window['label']}：分配到开发 {assigned_total} 个，已解决 {resolved_total} 个，"
        f"未解决 {unresolved_total} 个，重开事件 {reopened_events} 次，"
        f"新引入问题 {new_issue_count} 个，评估后转出 {transfer_out_issue_total} 个问题/{transfer_out_event_total} 次流转，"
        f"净变化 {net_change} 个。"
    )

    if team_period_summary:
        team_segments = [
            f"{row['team_name']} 已解决 {row['resolved_total']}/{row['total']}（{','.join(row.get('issue_keys') or []) or '-'}）"
            for row in team_period_summary
        ]
        summary_text = f"{summary_text} 团队概览：{'；'.join(team_segments)}。"

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
        "transfer_out": {
            "issue_count": transfer_out_issue_total,
            "event_count": transfer_out_event_total,
            "teams": team_summary,
            "note": "统计周期内团队内->团队外流转；若周期结束前回转到团队内则不计入问题数",
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
        "manager_summary_issue_keys": summary_issue_keys,
        "manager_summary_text": summary_text,
        "team_period_summary": team_period_summary,
        "team_summary": team_summary,
        "period_focus": period_focus,
    }
