from __future__ import annotations

from datetime import datetime
import re
from typing import Any


TODO_STATES = {"to do", "open", "backlog", "selected for development"}
IN_PROGRESS_STATES = {"in progress", "development", "testing"}
REVIEW_STATES = {"in review", "code review", "reviewing", "审核中"}
DONE_STATES = {"done", "resolved", "closed"}
SOLVING_STATES = {"solving", "解决中"}
MAINLINE_RESOLVED_STATES = {"主干已解决"}


def build_status_groups(status_mapping: dict[str, list[str]] | None = None) -> dict[str, set[str]]:
    defaults = {
        "todo": set(TODO_STATES),
        "in_progress": set(IN_PROGRESS_STATES),
        "review": set(REVIEW_STATES),
        "done": set(DONE_STATES),
    }
    if not status_mapping:
        return defaults

    groups = {key: set(values) for key, values in defaults.items()}
    for key in ("todo", "in_progress", "review", "done"):
        values = status_mapping.get(key, [])
        normalized = {(item or "").strip().lower() for item in values if str(item).strip()}
        if normalized:
            groups[key] = normalized
    return groups


def build_role_groups(role_settings: dict[str, list[str]] | None = None) -> dict[str, set[str]]:
    if not role_settings:
        return {
            "product_manager_roles": set(),
            "dev_manager_roles": set(),
            "developer_roles": set(),
            "quality_roles": set(),
        }

    return {
        "product_manager_roles": {
            (item or "").strip().lower() for item in (role_settings.get("product_manager_roles") or []) if str(item).strip()
        },
        "dev_manager_roles": {
            (item or "").strip().lower() for item in (role_settings.get("dev_manager_roles") or []) if str(item).strip()
        },
        "developer_roles": {
            (item or "").strip().lower() for item in (role_settings.get("developer_roles") or []) if str(item).strip()
        },
        "quality_roles": {
            (item or "").strip().lower() for item in (role_settings.get("quality_roles") or []) if str(item).strip()
        },
    }


def _derive_metric_owner(
    issue: dict[str, Any],
    assignee_name: str,
    assignee_login: str,
    role_settings: dict[str, list[str]] | None = None,
) -> str:
    role_groups = build_role_groups(role_settings)
    pm_roles = role_groups["product_manager_roles"]
    developer_roles = role_groups["developer_roles"]
    quality_roles = role_groups["quality_roles"]

    def find_last_assignee(match_roles: set[str]) -> str | None:
        histories = issue.get("changelog", {}).get("histories", [])
        sorted_histories = sorted(histories, key=lambda row: row.get("created", ""), reverse=True)
        for history in sorted_histories:
            for item in history.get("items", []):
                if (item.get("field") or "").lower() != "assignee":
                    continue
                to_login = (item.get("to") or "").strip()
                to_display = (item.get("toString") or item.get("to") or "").strip()
                if not to_display:
                    continue
                candidates = {to_display.lower(), to_login.lower()}
                if candidates.intersection(match_roles):
                    return to_display
        return None

    def find_last_non_quality_assignee() -> str | None:
        histories = issue.get("changelog", {}).get("histories", [])
        sorted_histories = sorted(histories, key=lambda row: row.get("created", ""), reverse=True)
        for history in sorted_histories:
            for item in history.get("items", []):
                if (item.get("field") or "").lower() != "assignee":
                    continue

                from_login = (item.get("from") or "").strip()
                from_display = (item.get("fromString") or item.get("from") or "").strip()
                if not from_display:
                    continue

                from_candidates = {from_display.lower(), from_login.lower()}
                if quality_roles and from_candidates.intersection(quality_roles):
                    continue
                return from_display
        return None

    current_candidates = {(assignee_name or "").strip().lower(), (assignee_login or "").strip().lower()}

    if quality_roles and current_candidates.intersection(quality_roles):
        if developer_roles:
            matched_developer = find_last_assignee(developer_roles)
            if matched_developer:
                return matched_developer
        fallback_owner = find_last_non_quality_assignee()
        if fallback_owner:
            return fallback_owner
        return assignee_name

    if not pm_roles:
        return assignee_name

    current_is_pm = bool(current_candidates.intersection(pm_roles))
    if not current_is_pm:
        return assignee_name

    if developer_roles:
        matched_developer = find_last_assignee(developer_roles)
        if matched_developer:
            return matched_developer

    histories = issue.get("changelog", {}).get("histories", [])
    sorted_histories = sorted(histories, key=lambda row: row.get("created", ""), reverse=True)
    for history in sorted_histories:
        for item in history.get("items", []):
            if (item.get("field") or "").lower() != "assignee":
                continue
            to_login = (item.get("to") or "").strip()
            to_display = (item.get("toString") or item.get("to") or "").strip()
            if not to_display:
                continue
            candidates = {to_display.lower(), to_login.lower()}
            if not candidates.intersection(pm_roles):
                return to_display

    return assignee_name


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    if re.search(r"[+-]\d{4}$", normalized):
        normalized = f"{normalized[:-5]}{normalized[-5:-2]}:{normalized[-2:]}"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def determine_column(status_name: str | None, status_groups: dict[str, set[str]] | None = None) -> str:
    groups = status_groups or build_status_groups()
    normalized = (status_name or "").strip().lower()
    if normalized in groups["done"]:
        return "Done"
    if normalized in groups["review"]:
        return "审核中"
    if normalized in groups["in_progress"]:
        return "In Progress"
    if normalized in groups["todo"]:
        return "To Do"
    return "To Do"


def extract_timeline(
    issue: dict[str, Any],
    status_groups: dict[str, set[str]] | None = None,
    role_settings: dict[str, list[str]] | None = None,
    teams: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    groups = status_groups or build_status_groups()
    fields = issue.get("fields", {})
    role_groups = build_role_groups(role_settings)
    pm_roles = role_groups["product_manager_roles"]
    dm_roles = role_groups["dev_manager_roles"]
    developer_roles = role_groups["developer_roles"]
    team_members = {
        (member or "").strip().lower()
        for team in (teams or [])
        for member in (team.get("members") or [])
        if str(member).strip()
    }

    timeline: dict[str, str | None] = {
        "created_at": fields.get("created"),
        "product_assigned_at": None,
        "product_assigned_to": None,
        "dev_manager_assigned_at": None,
        "dev_manager_assigned_from": None,
        "dev_manager_assigned_to": None,
        "developer_started_at": None,
        "in_progress_at": None,
        "review_at": None,
        "resolved_at": None,
        "closed_at": None,
    }
    timeline["reopened_events"] = []

    histories = issue.get("changelog", {}).get("histories", [])
    sorted_histories = sorted(histories, key=lambda row: row.get("created", ""))
    assign_count = 0

    for history in sorted_histories:
        changed_at = history.get("created")
        for item in history.get("items", []):
            field = (item.get("field") or "").lower()
            to_string = (item.get("toString") or "").strip().lower()
            if field == "assignee":
                assign_count += 1
                to_user = (item.get("to") or "").strip().lower()
                from_user = (item.get("from") or "").strip().lower()
                assignee_display = (item.get("toString") or item.get("to") or "").strip()
                from_display = (item.get("fromString") or item.get("from") or "").strip().lower()
                candidates = {to_string, to_user}
                from_candidates = {from_display, from_user}

                if developer_roles and not timeline["developer_started_at"] and candidates.intersection(developer_roles):
                    timeline["developer_started_at"] = changed_at

                if pm_roles:
                    if not timeline["product_assigned_at"] and candidates.intersection(pm_roles):
                        timeline["product_assigned_at"] = changed_at
                        timeline["product_assigned_to"] = assignee_display or None
                elif assign_count == 1 and not timeline["product_assigned_at"]:
                    timeline["product_assigned_at"] = changed_at
                    timeline["product_assigned_to"] = assignee_display or None

                if dm_roles and team_members:
                    if from_candidates.intersection(dm_roles) and candidates.intersection(team_members):
                        timeline["dev_manager_assigned_at"] = changed_at
                        timeline["dev_manager_assigned_from"] = (item.get("fromString") or item.get("from") or "").strip() or None
                        timeline["dev_manager_assigned_to"] = assignee_display or None

            if field == "status":
                from_string = (item.get("fromString") or "").strip().lower()
                if not timeline["in_progress_at"] and to_string in SOLVING_STATES:
                    timeline["in_progress_at"] = changed_at
                    if not timeline["developer_started_at"]:
                        timeline["developer_started_at"] = changed_at
                if not timeline["review_at"] and to_string in groups["review"]:
                    timeline["review_at"] = changed_at
                if not timeline["resolved_at"] and from_string in groups["review"] and to_string in MAINLINE_RESOLVED_STATES:
                    timeline["resolved_at"] = changed_at
                if not timeline["closed_at"] and to_string == "closed":
                    timeline["closed_at"] = changed_at
                if from_string in groups["done"] and to_string and to_string not in groups["done"] and changed_at:
                    timeline["reopened_events"].append(changed_at)

    if not timeline["resolved_at"]:
        current_status = (fields.get("status", {}).get("name") or "").strip().lower()
        if current_status in MAINLINE_RESOLVED_STATES:
            timeline["resolved_at"] = fields.get("resolutiondate")
            if not timeline["resolved_at"]:
                for history in sorted_histories:
                    changed_at = history.get("created")
                    for item in history.get("items", []):
                        if (item.get("field") or "").lower() != "status":
                            continue
                        from_string = (item.get("fromString") or "").strip().lower()
                        to_string = (item.get("toString") or "").strip().lower()
                        if from_string in groups["review"] and to_string == current_status:
                            timeline["resolved_at"] = changed_at
                            break
                    if timeline["resolved_at"]:
                        break
            if not timeline["resolved_at"]:
                for history in reversed(sorted_histories):
                    changed_at = history.get("created")
                    has_status_change = any((item.get("field") or "").lower() == "status" for item in history.get("items", []))
                    if has_status_change and changed_at:
                        timeline["resolved_at"] = changed_at
                        break

    return timeline


def extract_assignee_transfer_events(issue: dict[str, Any]) -> list[dict[str, str | None]]:
    histories = issue.get("changelog", {}).get("histories", [])
    sorted_histories = sorted(histories, key=lambda row: row.get("created", ""))
    events: list[dict[str, str | None]] = []

    for history in sorted_histories:
        changed_at = history.get("created")
        for item in history.get("items", []):
            field = (item.get("field") or "").lower()
            if field != "assignee":
                continue

            events.append(
                {
                    "at": changed_at,
                    "from_login": (item.get("from") or "").strip() or None,
                    "from_display": (item.get("fromString") or "").strip() or None,
                    "to_login": (item.get("to") or "").strip() or None,
                    "to_display": (item.get("toString") or "").strip() or None,
                }
            )

    return events


def normalize_issue(
    issue: dict[str, Any],
    base_url: str,
    status_mapping: dict[str, list[str]] | None = None,
    role_settings: dict[str, list[str]] | None = None,
    teams: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status_groups = build_status_groups(status_mapping)
    fields = issue.get("fields", {})
    status_name = fields.get("status", {}).get("name")
    priority_name = fields.get("priority", {}).get("name", "Unknown")
    assignee = fields.get("assignee", {}) or {}
    assignee_name = assignee.get("displayName") or "Unassigned"
    assignee_login = assignee.get("name") or assignee.get("key") or ""
    metric_owner = _derive_metric_owner(issue, assignee_name=assignee_name, assignee_login=assignee_login, role_settings=role_settings)

    timeline = extract_timeline(issue, status_groups=status_groups, role_settings=role_settings, teams=teams)
    assignee_transfer_events = extract_assignee_transfer_events(issue)
    return {
        "key": issue.get("key"),
        "summary": fields.get("summary", ""),
        "status": status_name,
        "column": determine_column(status_name, status_groups=status_groups),
        "assignee": assignee_name,
        "assignee_login": assignee_login,
        "metric_owner": metric_owner,
        "priority": priority_name,
        "issue_type": fields.get("issuetype", {}).get("name", "Unknown"),
        "description": fields.get("description") or "",
        "url": f"{base_url}/browse/{issue.get('key')}",
        "timeline": timeline,
        "assignee_transfer_events": assignee_transfer_events,
        "sprint": fields.get("sprint", {}).get("name") if isinstance(fields.get("sprint"), dict) else None,
    }


def filter_cards(
    cards: list[dict[str, Any]],
    assignee: str | None = None,
    priority: str | None = None,
    keyword: str | None = None,
) -> list[dict[str, Any]]:
    output = cards
    if assignee:
        output = [card for card in output if card["assignee"] == assignee]
    if priority:
        output = [card for card in output if card["priority"] == priority]
    if keyword:
        text = keyword.lower()
        output = [card for card in output if text in card["summary"].lower() or text in card["key"].lower()]
    return output


def split_columns(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    columns = {"To Do": [], "In Progress": [], "审核中": [], "Done": []}
    for card in cards:
        columns.setdefault(card["column"], []).append(card)
    return columns
