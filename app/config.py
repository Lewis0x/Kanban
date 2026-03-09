from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "jira_auth.yaml"


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
    }
