from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "jira_auth.yaml"


def normalize_task_owner_field_id(raw: Any) -> str | None:
    """将 task_owner 配置规范为 Jira REST 字段 id（如 customfield_12345）。

    支持：纯数字 ``12345`` → ``customfield_12345``；或已带前缀的 ``customfield_*`` 原样保留。
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.lower() == "auto":
        return None
    if s.isdigit():
        return f"customfield_{s}"
    return s


def load_config(config_path: str | None = None) -> dict[str, Any]:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        content = yaml.safe_load(file) or {}

    required = ["base_url", "username", "password"]
    missing = [key for key in required if not content.get(key)]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")

    filter_settings = content.get("filter_settings") or {}
    allowed_filter_ids = filter_settings.get("allowed_filter_ids") or []
    default_filter_id = filter_settings.get("default_filter_id")
    status_mapping = content.get("status_mapping") or {}
    role_settings = content.get("role_settings") or {}

    # Parse teams
    raw_teams = content.get("teams") or []
    teams: list[dict[str, Any]] = []
    for team in raw_teams:
        if not isinstance(team, dict):
            continue
        teams.append({
            "id": str(team.get("id") or "").strip(),
            "name": str(team.get("name") or "").strip(),
            "owner": str(team.get("owner") or "").strip(),
            "members": [str(m).strip() for m in (team.get("members") or []) if str(m).strip()],
        })

    # Parsed role lists
    pm_roles = [str(item).strip() for item in (role_settings.get("product_manager_roles") or []) if str(item).strip()]
    dm_roles = [str(item).strip() for item in (role_settings.get("dev_manager_roles") or []) if str(item).strip()]
    explicit_dev_roles = [str(item).strip() for item in (role_settings.get("developer_roles") or []) if str(item).strip()]
    qa_roles = [str(item).strip() for item in (role_settings.get("quality_roles") or []) if str(item).strip()]
    developer_logins = [
        str(item).strip() for item in (role_settings.get("developer_role_logins") or []) if str(item).strip()
    ]

    # Auto-derive developer_roles from teams.members when not explicitly configured
    developer_roles = list(dict.fromkeys(explicit_dev_roles))
    if not developer_roles and teams:
        non_dev_names = {name.lower() for name in pm_roles + dm_roles + qa_roles}
        for team in teams:
            for member in team["members"]:
                if member.lower() not in non_dev_names:
                    developer_roles.append(member)

    existing_lower = {x.lower() for x in developer_roles}
    for login in developer_logins:
        if login.lower() not in existing_lower:
            developer_roles.append(login)
            existing_lower.add(login.lower())

    return {
        "base_url": str(content["base_url"]).rstrip("/"),
        "username": content["username"],
        "password": content["password"],
        "verify_ssl": bool(content.get("verify_ssl", True)),
        "request_timeout_seconds": int(content.get("request_timeout_seconds", 30)),
        "jql_filters": [item.strip() for item in content.get("jql_filters", []) if str(item).strip()],
        "status_mapping": {
            "todo": [str(item).strip() for item in (status_mapping.get("todo") or []) if str(item).strip()],
            "in_progress": [
                str(item).strip() for item in (status_mapping.get("in_progress") or []) if str(item).strip()
            ],
            "review": [str(item).strip() for item in (status_mapping.get("review") or []) if str(item).strip()],
            "done": [str(item).strip() for item in (status_mapping.get("done") or []) if str(item).strip()],
        },
        "role_settings": {
            "product_manager_roles": pm_roles,
            "dev_manager_roles": dm_roles,
            "developer_roles": developer_roles,
            "quality_roles": qa_roles,
        },
        "teams": teams,
        "filter_settings": {
            "allowed_filter_ids": [str(item).strip() for item in allowed_filter_ids if str(item).strip()],
            "default_filter_id": str(default_filter_id).strip() if str(default_filter_id).strip() else None,
        },
        # 可选：Task Owner 自定义字段；支持 customfield_* 或纯数字 id
        "task_owner_field": normalize_task_owner_field_id(content.get("task_owner_field")),
    }
