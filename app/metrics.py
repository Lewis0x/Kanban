from __future__ import annotations

from statistics import mean
from typing import Any

from .normalize import parse_datetime


PRIORITY_WEIGHT = {
    "highest": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "lowest": 1,
}


def _normalize_identity(value: str | None) -> str:
    return (value or "").strip().lower()


def _build_team_membership(teams: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for team in teams or []:
        team_id = str(team.get("id") or "").strip()
        if not team_id:
            continue
        team_name = str(team.get("name") or team_id).strip() or team_id
        members = {
            _normalize_identity(str(member))
            for member in (team.get("members") or [])
            if str(member).strip()
        }
        output.append(
            {
                "id": team_id,
                "name": team_name,
                "members": members,
            }
        )
    return output


def _resolve_team_for_items(items: list[dict[str, Any]], teams: list[dict[str, Any]]) -> tuple[str, str]:
    identities: set[str] = set()
    for item in items:
        identities.add(_normalize_identity(str(item.get("metric_owner") or "")))
        identities.add(_normalize_identity(str(item.get("assignee") or "")))
        identities.add(_normalize_identity(str(item.get("assignee_login") or "")))

    for team in teams:
        members = team.get("members") or set()
        if any(identity and identity in members for identity in identities):
            return str(team.get("id") or ""), str(team.get("name") or "")

    return "other", "其他团队"


def _hours_between(start: str | None, end: str | None) -> float | None:
    start_dt = parse_datetime(start)
    end_dt = parse_datetime(end)
    if not start_dt or not end_dt:
        return None
    delta = end_dt - start_dt
    return delta.total_seconds() / 3600


def compute_member_metrics(cards: list[dict[str, Any]], teams: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    team_membership = _build_team_membership(teams)
    for card in cards:
        owner = str(card.get("metric_owner") or card.get("assignee") or "Unassigned")
        grouped.setdefault(owner, []).append(card)

    rows: list[dict[str, Any]] = []
    for assignee, items in grouped.items():
        team_id, team_name = _resolve_team_for_items(items, team_membership)
        total = len(items)
        resolved = len([item for item in items if item["column"] == "Done"])
        resolved_issue_keys = [
            str(item.get("key") or "")
            for item in items
            if item.get("column") == "Done" and str(item.get("key") or "").strip()
        ]
        wip = len([item for item in items if item["column"] in {"In Progress", "审核中"}])
        lead_times = [
            _hours_between(item["timeline"].get("created_at"), item["timeline"].get("resolved_at"))
            for item in items
        ]
        valid_lead_times = [value for value in lead_times if value is not None]

        total_weight = sum(PRIORITY_WEIGHT.get(item["priority"].lower(), 1) for item in items) or 1
        resolved_weight = sum(
            PRIORITY_WEIGHT.get(item["priority"].lower(), 1) for item in items if item["column"] == "Done"
        )

        rows.append(
            {
                "team_id": team_id,
                "team_name": team_name,
                "assignee": assignee,
                "total": total,
                "resolved": resolved,
                "resolved_issue_keys": sorted(set(resolved_issue_keys)),
                "resolution_rate": round((resolved / total) * 100, 2) if total else 0,
                "wip": wip,
                "avg_lead_time_hours": round(mean(valid_lead_times), 2) if valid_lead_times else None,
                "weighted_progress": round((resolved_weight / total_weight) * 100, 2),
            }
        )

    rows.sort(
        key=lambda row: (
            row["team_name"] == "其他团队",
            row["team_name"],
            -row["weighted_progress"],
            row["assignee"],
        )
    )
    return rows


def build_gantt_rows(cards: list[dict[str, Any]], mode: str = "member") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in cards:
        start = card["timeline"].get("developer_started_at") if mode == "member" else card["timeline"].get("created_at")
        end = card["timeline"].get("resolved_at")
        lane = str(card.get("metric_owner") or card.get("assignee") or "Unassigned") if mode == "member" else (card.get("sprint") or "Unknown Sprint")

        if not start or not end:
            continue

        rows.append(
            {
                "lane": lane,
                "key": card["key"],
                "summary": card["summary"],
                "priority": card["priority"],
                "status": card["status"],
                "start": start,
                "end": end,
                "url": card["url"],
            }
        )

    rows.sort(key=lambda row: (row["lane"], row["start"]))
    return rows
