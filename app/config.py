from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "jira_auth.yaml"


def _normalize_user_list(values: list[Any] | None) -> list[str]:
    return [str(item).strip() for item in (values or []) if str(item).strip()]


def _normalize_teams(raw_teams: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_teams, list):
        return []

    teams: list[dict[str, Any]] = []
    for index, raw_team in enumerate(raw_teams):
        if not isinstance(raw_team, dict):
            continue

        team_id = str(raw_team.get("id") or "").strip()
        team_name = str(raw_team.get("name") or "").strip()
        owner = str(raw_team.get("owner") or "").strip()
        members = _normalize_user_list(raw_team.get("members"))

        if not team_id:
            if team_name:
                team_id = team_name
            else:
                team_id = f"team_{index + 1}"

        teams.append(
            {
                "id": team_id,
                "name": team_name or team_id,
                "owner": owner,
                "members": members,
            }
        )

    return teams


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
    teams = _normalize_teams(content.get("teams"))

    return {
        "base_url": str(content["base_url"]).rstrip("/"),
        "username": content["username"],
        "password": content["password"],
        "verify_ssl": bool(content.get("verify_ssl", True)),
        "request_timeout_seconds": int(content.get("request_timeout_seconds", 30)),
        "jql_filters": [item.strip() for item in content.get("jql_filters", []) if str(item).strip()],
        "status_mapping": {
            "todo": _normalize_user_list(status_mapping.get("todo")),
            "in_progress": [
                str(item).strip() for item in (status_mapping.get("in_progress") or []) if str(item).strip()
            ],
            "review": _normalize_user_list(status_mapping.get("review")),
            "done": _normalize_user_list(status_mapping.get("done")),
        },
        "role_settings": {
            "product_manager_roles": [
                str(item).strip() for item in (role_settings.get("product_manager_roles") or []) if str(item).strip()
            ],
            "dev_manager_roles": [
                str(item).strip() for item in (role_settings.get("dev_manager_roles") or []) if str(item).strip()
            ],
            "developer_roles": [
                str(item).strip() for item in (role_settings.get("developer_roles") or []) if str(item).strip()
            ],
            "quality_roles": [
                str(item).strip() for item in (role_settings.get("quality_roles") or []) if str(item).strip()
            ],
        },
        "filter_settings": {
            "allowed_filter_ids": [str(item).strip() for item in allowed_filter_ids if str(item).strip()],
            "default_filter_id": str(default_filter_id).strip() if str(default_filter_id).strip() else None,
        },
        "teams": teams,
    }
