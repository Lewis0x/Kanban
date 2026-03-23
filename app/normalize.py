from __future__ import annotations

import re
from datetime import datetime
from typing import Any


_TZ_NO_COLON = re.compile(r'([+-])(\d{2})(\d{2})$')


TODO_STATES = {"to do", "open", "backlog", "selected for development"}
IN_PROGRESS_STATES = {"in progress", "development", "testing"}
REVIEW_STATES = {"in review", "code review", "reviewing", "审核中"}
DONE_STATES = {"done", "resolved", "closed", "已解决"}


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


def _extract_task_owner_display(fields: dict[str, Any], field_id: str | None) -> str | None:
    """从 Jira 自定义字段（用户选择器等）解析展示名；field_id 如 customfield_10400。"""
    if not field_id or not str(field_id).strip():
        return None
    fid = str(field_id).strip()
    raw = fields.get(fid)
    if raw is None:
        return None
    if isinstance(raw, dict):
        name = (raw.get("displayName") or raw.get("name") or "").strip()
        return name or None
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict):
            name = (first.get("displayName") or first.get("name") or "").strip()
            return name or None
        if isinstance(first, str) and first.strip():
            return first.strip()
    return None


def _is_task_owner_changelog_field(field_name: str) -> bool:
    """Jira changelog 里自定义字段的 `field` 可能是英文名或实例本地化名（如中文）。"""
    n = (field_name or "").strip()
    if not n:
        return False
    if n.lower() == "task owner":
        return True
    # 部分 Jira 实例在 changelog 中使用中文显示名，与 REST fields 的 customfield 无关
    if n == "任务负责人":
        return True
    return False


def _extract_latest_task_owner_from_changelog(issue: dict[str, Any]) -> str | None:
    """从 changelog 中按时间顺序取 Task Owner / 任务负责人 的当前值（最后一次变更后的结果）。"""
    histories = issue.get("changelog", {}).get("histories", [])
    if not histories:
        return None
    sorted_histories = sorted(histories, key=lambda row: row.get("created", "") or "")
    current: str | None = None
    for history in sorted_histories:
        for item in history.get("items", []):
            fname = (item.get("field") or "").strip()
            if not _is_task_owner_changelog_field(fname):
                continue
            to_display = (item.get("toString") or item.get("to") or "").strip()
            if to_display in ("", "-"):
                current = None
            else:
                current = to_display
    return current


def _derive_metric_owner(
    issue: dict[str, Any],
    assignee_name: str,
    assignee_login: str,
    role_settings: dict[str, list[str]] | None = None,
) -> str:
    role_groups = build_role_groups(role_settings)
    pm_roles = role_groups["product_manager_roles"]
    dm_roles = role_groups["dev_manager_roles"]
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

    current_candidates = {(assignee_name or "").strip().lower(), (assignee_login or "").strip().lower()}

    if quality_roles and current_candidates.intersection(quality_roles):
        if developer_roles:
            matched_developer = find_last_assignee(developer_roles)
            if matched_developer:
                return matched_developer

        # developer_roles not configured or no match — fall back to the last
        # assignee who is not in any management / QA role (i.e. the developer).
        non_dev_roles = quality_roles | pm_roles | dm_roles
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
                if not candidates.intersection(non_dev_roles):
                    return to_display

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
    # JIRA returns offsets like +0800; fromisoformat needs +08:00
    normalized = _TZ_NO_COLON.sub(r'\1\2:\3', normalized)
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def determine_column(
    status_name: str | None,
    status_groups: dict[str, set[str]] | None = None,
    *,
    resolution_date: str | None = None,
) -> str:
    """划分看板列。若状态名未出现在 status_mapping 任一列，但 Jira 已填写 resolutiondate，则视为已解决 → Done。"""
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
    if resolution_date:
        return "Done"
    return "To Do"


def extract_timeline(
    issue: dict[str, Any],
    status_groups: dict[str, set[str]] | None = None,
    role_settings: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    groups = status_groups or build_status_groups()
    fields = issue.get("fields", {})
    role_groups = build_role_groups(role_settings)
    pm_roles = role_groups["product_manager_roles"]
    dm_roles = role_groups["dev_manager_roles"]
    developer_roles = role_groups["developer_roles"]

    timeline: dict[str, str | None] = {
        "created_at": fields.get("created"),
        "product_assigned_at": None,
        "product_assigned_to": None,
        "dev_manager_assigned_at": None,
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
                assignee_display = (item.get("toString") or item.get("to") or "").strip()
                candidates = {to_string, to_user}

                if developer_roles and not timeline["developer_started_at"] and candidates.intersection(developer_roles):
                    timeline["developer_started_at"] = changed_at

                if pm_roles:
                    if not timeline["product_assigned_at"] and candidates.intersection(pm_roles):
                        timeline["product_assigned_at"] = changed_at
                        timeline["product_assigned_to"] = assignee_display or None
                elif assign_count == 1 and not timeline["product_assigned_at"]:
                    timeline["product_assigned_at"] = changed_at
                    timeline["product_assigned_to"] = assignee_display or None

                if dm_roles:
                    if not timeline["dev_manager_assigned_at"] and candidates.intersection(dm_roles):
                        timeline["dev_manager_assigned_at"] = changed_at
                        timeline["dev_manager_assigned_to"] = assignee_display or None
                elif assign_count == 2 and not timeline["dev_manager_assigned_at"]:
                    timeline["dev_manager_assigned_at"] = changed_at
                    timeline["dev_manager_assigned_to"] = assignee_display or None

            if field == "status":
                from_string = (item.get("fromString") or "").strip().lower()
                if not timeline["in_progress_at"] and to_string in groups["in_progress"]:
                    timeline["in_progress_at"] = changed_at
                if not timeline["review_at"] and to_string in groups["review"]:
                    timeline["review_at"] = changed_at
                if to_string in groups["done"]:
                    timeline["resolved_at"] = changed_at
                # 「已关闭 / Closed」单独记时点，供周期总结：解决与关闭分步时仍可按关闭时间入总结
                raw_disp = (item.get("toString") or "").strip()
                rl = raw_disp.lower()
                if to_string in groups["done"] and (
                    rl == "closed"
                    or raw_disp == "已关闭"
                    or "已关闭" in raw_disp
                ):
                    timeline["closed_at"] = changed_at
                if from_string in groups["done"] and to_string and to_string not in groups["done"] and changed_at:
                    timeline["reopened_events"].append(changed_at)

    if not timeline["resolved_at"]:
        current_status = (fields.get("status", {}).get("name") or "").strip().lower()
        if current_status in groups["done"]:
            timeline["resolved_at"] = fields.get("resolutiondate")
            if not timeline["resolved_at"]:
                for history in sorted_histories:
                    changed_at = history.get("created")
                    for item in history.get("items", []):
                        if (item.get("field") or "").lower() != "status":
                            continue
                        to_string = (item.get("toString") or "").strip().lower()
                        if to_string == current_status:
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

    if not timeline["resolved_at"] and fields.get("resolutiondate"):
        timeline["resolved_at"] = fields.get("resolutiondate")

    if not timeline["closed_at"]:
        st_name = (fields.get("status", {}) or {}).get("name") or ""
        if "已关闭" in st_name or st_name.strip().lower() == "closed":
            timeline["closed_at"] = timeline.get("resolved_at") or fields.get("resolutiondate")

    return timeline


def normalize_issue(
    issue: dict[str, Any],
    base_url: str,
    status_mapping: dict[str, list[str]] | None = None,
    role_settings: dict[str, list[str]] | None = None,
    task_owner_field: str | None = None,
) -> dict[str, Any]:
    status_groups = build_status_groups(status_mapping)
    fields = issue.get("fields", {})
    status_name = fields.get("status", {}).get("name")
    priority_name = fields.get("priority", {}).get("name", "Unknown")
    assignee = fields.get("assignee", {}) or {}
    assignee_name = assignee.get("displayName") or "Unassigned"
    assignee_login = assignee.get("name") or assignee.get("key") or ""
    metric_owner = _derive_metric_owner(issue, assignee_name=assignee_name, assignee_login=assignee_login, role_settings=role_settings)
    task_owner = _extract_task_owner_display(fields, task_owner_field)
    if not task_owner:
        task_owner = _extract_latest_task_owner_from_changelog(issue)
    if task_owner:
        metric_owner = task_owner

    timeline = extract_timeline(issue, status_groups=status_groups, role_settings=role_settings)
    return {
        "key": issue.get("key"),
        "summary": fields.get("summary", ""),
        "status": status_name,
        "column": determine_column(
            status_name,
            status_groups=status_groups,
            resolution_date=fields.get("resolutiondate"),
        ),
        "assignee": assignee_name,
        "metric_owner": metric_owner,
        "task_owner": task_owner,
        "priority": priority_name,
        "issue_type": fields.get("issuetype", {}).get("name", "Unknown"),
        "description": fields.get("description") or "",
        "url": f"{base_url}/browse/{issue.get('key')}",
        "timeline": timeline,
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
        output = [
            card for card in output
            if card["assignee"] == assignee or card.get("metric_owner") == assignee
        ]
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
