from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file
from matplotlib import pyplot as plt
from openpyxl import Workbook

from .config import load_config
from .jira_client import JiraClient, JiraClientError, JiraConfig
from .analytics import build_assignment_debug, build_manager_summary
from .metrics import build_gantt_rows, compute_member_metrics
from .normalize import extract_assignee_transfer_events, filter_cards, normalize_issue, split_columns
from .period import resolve_period_window


def create_app(config_path: str | None = None, jira_client: JiraClient | None = None) -> Flask:
    app = Flask(__name__, template_folder="../templates", static_folder="../static")
    cfg = load_config(config_path) if jira_client is None else None

    def get_runtime_config() -> dict[str, Any] | None:
        if jira_client is not None:
            return cfg
        return load_config(config_path)

    def get_runtime_client(runtime_cfg: dict[str, Any] | None = None) -> JiraClient:
        if jira_client is not None:
            return jira_client

        resolved_cfg = runtime_cfg or get_runtime_config() or {}
        return JiraClient(
            JiraConfig(
                base_url=resolved_cfg["base_url"],
                username=resolved_cfg["username"],
                password=resolved_cfg["password"],
                verify_ssl=resolved_cfg["verify_ssl"],
                timeout_seconds=resolved_cfg["request_timeout_seconds"],
                jql_filters=resolved_cfg.get("jql_filters", []),
            )
        )

    cache_dir = Path(__file__).resolve().parent.parent / "storage" / "jira_query_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    history_file = Path(__file__).resolve().parent.parent / "storage" / "team_issue_history.json"

    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat()

    def _normalize_identity(value: str | None) -> str:
        return (value or "").strip().lower()

    def _build_team_membership(runtime_cfg: dict[str, Any] | None = None) -> dict[str, set[str]]:
        teams = (runtime_cfg or {}).get("teams") or []
        membership: dict[str, set[str]] = {}
        for team in teams:
            team_id = str(team.get("id") or "").strip()
            if not team_id:
                continue
            membership[team_id] = {
                _normalize_identity(str(member))
                for member in (team.get("members") or [])
                if str(member).strip()
            }
        return membership

    def _read_history_store() -> dict[str, Any]:
        if not history_file.exists():
            return {"updated_at": _now_iso(), "queries": [], "issues": {}}
        try:
            payload = json.loads(history_file.read_text(encoding="utf-8"))
        except Exception:
            return {"updated_at": _now_iso(), "queries": [], "issues": {}}
        if not isinstance(payload, dict):
            return {"updated_at": _now_iso(), "queries": [], "issues": {}}
        payload.setdefault("queries", [])
        payload.setdefault("issues", {})
        return payload

    def _write_history_store(payload: dict[str, Any]) -> None:
        payload["updated_at"] = _now_iso()
        history_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    def _merge_unique_events(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[tuple[str, str, str]] = set()
        merged: list[dict[str, Any]] = []
        for row in existing + incoming:
            key = (
                str(row.get("at") or ""),
                str(row.get("from_login") or row.get("from") or ""),
                str(row.get("to_login") or row.get("to") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(row)
        merged.sort(key=lambda row: str(row.get("at") or ""))
        return merged

    def _summarize_team_touch(issue: dict[str, Any], team_membership: dict[str, set[str]]) -> tuple[list[str], bool, list[dict[str, Any]], list[dict[str, Any]]]:
        fields = issue.get("fields", {})
        assignee = fields.get("assignee") or {}
        current_identities = {
            _normalize_identity(assignee.get("name") or assignee.get("key")),
            _normalize_identity(assignee.get("displayName")),
        }

        raw_events = extract_assignee_transfer_events(issue)
        normalized_events: list[dict[str, Any]] = []
        entered_events: list[dict[str, Any]] = []
        touched_teams: set[str] = set()
        ever_in_team = False

        for event in raw_events:
            from_identity = _normalize_identity(event.get("from_login") or event.get("from_display"))
            to_identity = _normalize_identity(event.get("to_login") or event.get("to_display"))

            normalized_events.append(
                {
                    "at": event.get("at"),
                    "from_login": event.get("from_login"),
                    "from_display": event.get("from_display"),
                    "to_login": event.get("to_login"),
                    "to_display": event.get("to_display"),
                }
            )

            for team_id, members in team_membership.items():
                from_in = bool(from_identity and from_identity in members)
                to_in = bool(to_identity and to_identity in members)
                current_in = any(identity and identity in members for identity in current_identities)
                if from_in or to_in or current_in:
                    touched_teams.add(team_id)
                    ever_in_team = True
                if to_in:
                    entered_events.append(
                        {
                            "team_id": team_id,
                            "at": event.get("at"),
                            "from": event.get("from_display") or event.get("from_login"),
                            "to": event.get("to_display") or event.get("to_login"),
                        }
                    )

        for team_id, members in team_membership.items():
            if any(identity and identity in members for identity in current_identities):
                touched_teams.add(team_id)
                ever_in_team = True

        return sorted(touched_teams), ever_in_team, normalized_events, entered_events

    def update_team_issue_history(
        issues: list[dict[str, Any]],
        custom_jql: str | None,
        jql_preview: str,
        cache_file_name: str,
        runtime_cfg: dict[str, Any] | None = None,
    ) -> None:
        history = _read_history_store()
        queries = history.get("queries") if isinstance(history.get("queries"), list) else []
        issues_map = history.get("issues") if isinstance(history.get("issues"), dict) else {}

        queries.append(
            {
                "queried_at": _now_iso(),
                "custom_jql": custom_jql or "",
                "jql_preview": jql_preview,
                "issue_count": len(issues),
                "cache_file": cache_file_name,
            }
        )
        history["queries"] = queries[-300:]

        membership = _build_team_membership(runtime_cfg)
        base_url = (runtime_cfg or {}).get("base_url") or "https://jira.local"

        for issue in issues:
            key = str(issue.get("key") or "").strip()
            if not key:
                continue

            fields = issue.get("fields", {})
            assignee = fields.get("assignee") or {}
            touched_teams, ever_in_team, transfer_events, entered_events = _summarize_team_touch(issue, membership)

            existing = issues_map.get(key) if isinstance(issues_map.get(key), dict) else {}
            existing_teams = existing.get("teams_touched") if isinstance(existing.get("teams_touched"), list) else []
            merged_teams = sorted({*(str(item) for item in existing_teams), *touched_teams})

            existing_transfer = existing.get("assignee_transfer_events") if isinstance(existing.get("assignee_transfer_events"), list) else []
            existing_entered = existing.get("entered_team_events") if isinstance(existing.get("entered_team_events"), list) else []

            issues_map[key] = {
                "key": key,
                "summary": fields.get("summary") or existing.get("summary") or "",
                "url": f"{base_url}/browse/{key}",
                "assignee": assignee.get("displayName") or existing.get("assignee") or "Unassigned",
                "assignee_login": assignee.get("name") or assignee.get("key") or existing.get("assignee_login") or "",
                "status": (fields.get("status") or {}).get("name") or existing.get("status") or "",
                "first_seen_at": existing.get("first_seen_at") or _now_iso(),
                "last_seen_at": _now_iso(),
                "seen_count": int(existing.get("seen_count", 0)) + 1,
                "last_jql_preview": jql_preview,
                "teams_touched": merged_teams,
                "ever_in_team": bool(existing.get("ever_in_team", False) or ever_in_team),
                "assignee_transfer_events": _merge_unique_events(existing_transfer, transfer_events),
                "entered_team_events": _merge_unique_events(existing_entered, entered_events),
            }

        history["issues"] = issues_map
        _write_history_store(history)

    def build_historical_cards_for_window() -> list[dict[str, Any]]:
        history = _read_history_store()
        issues_map = history.get("issues") if isinstance(history.get("issues"), dict) else {}
        cards: list[dict[str, Any]] = []
        for issue in issues_map.values():
            if not isinstance(issue, dict):
                continue
            if not issue.get("ever_in_team"):
                continue
            cards.append(
                {
                    "key": issue.get("key"),
                    "summary": issue.get("summary") or "",
                    "status": issue.get("status") or "",
                    "assignee": issue.get("assignee") or "Unassigned",
                    "assignee_login": issue.get("assignee_login") or "",
                    "metric_owner": issue.get("assignee") or "Unassigned",
                    "url": issue.get("url") or "",
                    "timeline": {
                        "created_at": issue.get("first_seen_at"),
                        "developer_started_at": None,
                        "resolved_at": None,
                        "reopened_events": [],
                    },
                    "assignee_transfer_events": issue.get("assignee_transfer_events") or [],
                }
            )
        return cards

    def merge_transfer_out_summary(primary: dict[str, Any], supplement: dict[str, Any]) -> dict[str, Any]:
        primary_cards = primary.get("manager_summary_cards") or {}
        primary_issue_keys = primary.get("manager_summary_issue_keys") or {}
        primary_focus = primary.get("period_focus") or {}
        primary_transfer = primary_focus.get("transfer_out") or {}
        primary_team_period = primary.get("team_period_summary") or []

        supplement_cards = supplement.get("manager_summary_cards") or {}
        supplement_issue_keys = supplement.get("manager_summary_issue_keys") or {}
        supplement_focus = supplement.get("period_focus") or {}
        supplement_transfer = supplement_focus.get("transfer_out") or {}
        supplement_team_period = supplement.get("team_period_summary") or []

        primary_cards["transfer_out_issue_total"] = int(primary_cards.get("transfer_out_issue_total", 0)) + int(
            supplement_cards.get("transfer_out_issue_total", 0)
        )
        primary_cards["transfer_out_event_total"] = int(primary_cards.get("transfer_out_event_total", 0)) + int(
            supplement_cards.get("transfer_out_event_total", 0)
        )
        merged_transfer_out_keys = sorted(
            {
                str(key).strip()
                for key in (primary_issue_keys.get("transfer_out") or []) + (supplement_issue_keys.get("transfer_out") or [])
                if str(key).strip()
            }
        )
        primary_issue_keys["transfer_out"] = merged_transfer_out_keys

        teams_by_id: dict[str, dict[str, Any]] = {}
        for row in (primary_transfer.get("teams") or []) + (supplement_transfer.get("teams") or []):
            team_id = str(row.get("team_id") or "").strip()
            if not team_id:
                continue
            existing = teams_by_id.get(team_id)
            if existing is None:
                teams_by_id[team_id] = {
                    "team_id": row.get("team_id"),
                    "team_name": row.get("team_name"),
                    "owner": row.get("owner", ""),
                    "member_count": row.get("member_count", 0),
                    "transfer_out_issue_count": int(row.get("transfer_out_issue_count", 0)),
                    "transfer_out_event_count": int(row.get("transfer_out_event_count", 0)),
                    "items": list(row.get("items") or []),
                }
                continue

            existing["transfer_out_issue_count"] += int(row.get("transfer_out_issue_count", 0))
            existing["transfer_out_event_count"] += int(row.get("transfer_out_event_count", 0))
            existing["items"].extend(list(row.get("items") or []))

        for team_row in teams_by_id.values():
            items = team_row.get("items") or []
            seen_keys: set[str] = set()
            deduped_items: list[dict[str, Any]] = []
            for item in sorted(items, key=lambda item_row: str(item_row.get("latest_transfer_out_at") or ""), reverse=True):
                key = str(item.get("key") or "")
                marker = f"{key}|{item.get('latest_transfer_out_at') or ''}"
                if marker in seen_keys:
                    continue
                seen_keys.add(marker)
                deduped_items.append(item)
            team_row["items"] = deduped_items

        merged_teams = sorted(teams_by_id.values(), key=lambda row: str(row.get("team_name") or row.get("team_id") or ""))
        primary_transfer["teams"] = merged_teams
        primary_transfer["issue_count"] = int(primary_transfer.get("issue_count", 0)) + int(supplement_transfer.get("issue_count", 0))
        primary_transfer["event_count"] = int(primary_transfer.get("event_count", 0)) + int(supplement_transfer.get("event_count", 0))
        if supplement_transfer.get("note"):
            note = str(primary_transfer.get("note") or "")
            if "历史查询" not in note:
                primary_transfer["note"] = f"{note}；含历史查询补偿"

        team_period_by_id: dict[str, dict[str, Any]] = {}
        for row in list(primary_team_period) + list(supplement_team_period):
            team_id = str(row.get("team_id") or "").strip() or "other"
            existing = team_period_by_id.get(team_id)
            if existing is None:
                team_period_by_id[team_id] = {
                    "team_id": row.get("team_id") or team_id,
                    "team_name": row.get("team_name") or team_id,
                    "total": int(row.get("total", 0)),
                    "assigned_total": int(row.get("assigned_total", 0)),
                    "resolved_total": int(row.get("resolved_total", 0)),
                    "unresolved_total": int(row.get("unresolved_total", 0)),
                    "issue_keys": list(row.get("issue_keys") or []),
                }
                continue

            existing["total"] += int(row.get("total", 0))
            existing["assigned_total"] += int(row.get("assigned_total", 0))
            existing["resolved_total"] += int(row.get("resolved_total", 0))
            existing["unresolved_total"] += int(row.get("unresolved_total", 0))
            existing["issue_keys"].extend(list(row.get("issue_keys") or []))

        merged_team_period = []
        for row in team_period_by_id.values():
            row["issue_keys"] = sorted({str(key).strip() for key in row.get("issue_keys") or [] if str(key).strip()})
            merged_team_period.append(row)
        merged_team_period.sort(key=lambda row: (str(row.get("team_name") or "") == "其他团队", str(row.get("team_name") or "")))

        primary["manager_summary_cards"] = primary_cards
        primary["manager_summary_issue_keys"] = primary_issue_keys
        primary_focus["transfer_out"] = primary_transfer
        primary["period_focus"] = primary_focus
        primary["team_period_summary"] = merged_team_period
        return primary

    def build_jql_preview(custom_jql: str | None, runtime_cfg: dict[str, Any] | None = None) -> str:
        runtime_client = get_runtime_client(runtime_cfg)
        if hasattr(runtime_client, "build_search_jql"):
            return str(runtime_client.build_search_jql(custom_jql))
        if custom_jql:
            return f"({custom_jql})"
        return ""

    def get_cache_file(custom_jql: str | None, runtime_cfg: dict[str, Any] | None = None) -> Path:
        key_source = build_jql_preview(custom_jql, runtime_cfg=runtime_cfg)
        key = hashlib.sha256(key_source.encode("utf-8")).hexdigest()
        return cache_dir / f"{key}.json"

    def query_and_cache_issues(custom_jql: str | None, runtime_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
        runtime_client = get_runtime_client(runtime_cfg)
        issues = runtime_client.get_issues_by_jql(jql=custom_jql)
        queried_at = _now_iso()
        payload = {
            "custom_jql": custom_jql,
            "jql_preview": build_jql_preview(custom_jql, runtime_cfg=runtime_cfg),
            "queried_at": queried_at,
            "issue_count": len(issues),
            "issues": issues,
        }
        cache_file = get_cache_file(custom_jql, runtime_cfg=runtime_cfg)
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        update_team_issue_history(
            issues,
            custom_jql=custom_jql,
            jql_preview=str(payload.get("jql_preview", "")),
            cache_file_name=cache_file.name,
            runtime_cfg=runtime_cfg,
        )
        return payload

    def list_cache_sources(runtime_cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        for cache_file in cache_dir.glob("*.json"):
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            custom_jql_value = payload.get("custom_jql")
            custom_jql = str(custom_jql_value).strip() if custom_jql_value else None
            jql_preview = str(payload.get("jql_preview") or build_jql_preview(custom_jql, runtime_cfg=runtime_cfg))

            sources.append(
                {
                    "id": cache_file.stem,
                    "issue_count": int(payload.get("issue_count", 0)),
                    "jql_preview": jql_preview,
                    "custom_jql": custom_jql or "",
                    "updated_at": cache_file.stat().st_mtime,
                }
            )

        return sorted(sources, key=lambda row: row["updated_at"], reverse=True)

    def load_cached_issues(
        custom_jql: str | None,
        source_mode: str = "auto",
        cache_id: str | None = None,
        runtime_cfg: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        normalized_source = (source_mode or "auto").strip().lower()

        if normalized_source == "cache_id" and cache_id:
            cache_file = cache_dir / f"{cache_id}.json"
            if not cache_file.exists():
                raise FileNotFoundError("Query cache not found")
            return (
                json.loads(cache_file.read_text(encoding="utf-8")),
                {
                    "cache_source": f"storage/jira_query_cache/{cache_file.name}",
                    "cache_mode": normalized_source,
                    "cache_id": cache_file.stem,
                    "cache_fallback": False,
                },
            )

        if normalized_source == "latest":
            sources = list_cache_sources(runtime_cfg=runtime_cfg)
            if not sources:
                raise FileNotFoundError("Query cache not found")
            latest_id = str(sources[0]["id"])
            cache_file = cache_dir / f"{latest_id}.json"
            return (
                json.loads(cache_file.read_text(encoding="utf-8")),
                {
                    "cache_source": f"storage/jira_query_cache/{cache_file.name}",
                    "cache_mode": normalized_source,
                    "cache_id": latest_id,
                    "cache_fallback": False,
                },
            )

        requested_cache = get_cache_file(custom_jql, runtime_cfg=runtime_cfg)
        if requested_cache.exists():
            return (
                json.loads(requested_cache.read_text(encoding="utf-8")),
                {
                    "cache_source": f"storage/jira_query_cache/{requested_cache.name}",
                    "cache_mode": normalized_source,
                    "cache_id": requested_cache.stem,
                    "cache_fallback": False,
                },
            )

        if normalized_source == "requested":
            raise FileNotFoundError("Query cache not found")

        sources = list_cache_sources(runtime_cfg=runtime_cfg)
        if not sources:
            raise FileNotFoundError("Query cache not found")

        latest_id = str(sources[0]["id"])
        cache_file = cache_dir / f"{latest_id}.json"
        return (
            json.loads(cache_file.read_text(encoding="utf-8")),
            {
                "cache_source": f"storage/jira_query_cache/{cache_file.name}",
                "cache_mode": normalized_source,
                "cache_id": latest_id,
                "cache_fallback": True,
            },
        )

    def list_cached_queries(runtime_cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        latest_by_jql: dict[str, dict[str, Any]] = {}
        for cache_file in cache_dir.glob("*.json"):
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                continue

            custom_jql_value = payload.get("custom_jql")
            custom_jql = str(custom_jql_value).strip() if custom_jql_value else None
            expected_preview = build_jql_preview(custom_jql, runtime_cfg=runtime_cfg)
            if str(payload.get("jql_preview", "")) != expected_preview:
                continue

            current = {
                "id": cache_file.stem,
                "name": expected_preview,
                "issue_count": int(payload.get("issue_count", 0)),
                "jql_preview": str(payload.get("jql_preview", "")),
                "custom_jql": custom_jql or "",
                "updated_at": cache_file.stat().st_mtime,
            }

            previous = latest_by_jql.get(expected_preview)
            if previous is None or current["updated_at"] > previous["updated_at"]:
                latest_by_jql[expected_preview] = current

        return sorted(latest_by_jql.values(), key=lambda row: row["updated_at"], reverse=True)

    def get_cards(
        assignee: str | None,
        priority: str | None,
        keyword: str | None,
        custom_jql: str | None,
        source_mode: str = "auto",
        cache_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
        runtime_cfg = get_runtime_config()
        payload, cache_meta = load_cached_issues(
            custom_jql,
            source_mode=source_mode,
            cache_id=cache_id,
            runtime_cfg=runtime_cfg,
        )
        issues = payload.get("issues", [])
        base_url = (runtime_cfg or {}).get("base_url") or "https://jira.local"
        status_mapping = (runtime_cfg or {}).get("status_mapping")
        role_settings = (runtime_cfg or {}).get("role_settings")
        teams = (runtime_cfg or {}).get("teams") or []
        cards = [
            normalize_issue(
                issue,
                base_url=base_url,
                status_mapping=status_mapping,
                role_settings=role_settings,
                teams=teams,
            )
            for issue in issues
        ]
        return (
            filter_cards(cards, assignee=assignee, priority=priority, keyword=keyword),
            str(payload.get("jql_preview", "")),
            cache_meta,
        )

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/cached_queries")
    def api_cached_queries():
        runtime_cfg = get_runtime_config()
        queries = list_cached_queries(runtime_cfg=runtime_cfg)
        default_jql = ""
        if queries:
            default_jql = str(queries[0].get("custom_jql", ""))
        return jsonify({"queries": queries, "default_jql": default_jql})

    @app.get("/api/cache_sources")
    def api_cache_sources():
        runtime_cfg = get_runtime_config()
        return jsonify({"sources": list_cache_sources(runtime_cfg=runtime_cfg)})

    @app.get("/api/history/team_issues")
    def api_team_issue_history():
        history = _read_history_store()
        issues = history.get("issues") if isinstance(history.get("issues"), dict) else {}
        queries = history.get("queries") if isinstance(history.get("queries"), list) else []
        return jsonify(
            {
                "updated_at": history.get("updated_at"),
                "query_count": len(queries),
                "issue_count": len(issues),
                "queries": queries[-50:],
                "issues": list(issues.values()),
            }
        )

    @app.post("/api/query")
    @app.get("/api/query")
    def api_query():
        confirmed = (request.args.get("confirmed") or "").strip().lower() == "true"
        if not confirmed:
            return jsonify({"error": "Jira query requires confirmation. Set confirmed=true."}), 400

        custom_jql = request.args.get("jql")
        runtime_cfg = get_runtime_config()
        try:
            payload = query_and_cache_issues(custom_jql, runtime_cfg=runtime_cfg)
        except JiraClientError as error:
            return jsonify({"error": str(error)}), 502

        return jsonify(
            {
                "issue_count": payload.get("issue_count", 0),
                "jql_preview": payload.get("jql_preview", ""),
                "cache_file": str(get_cache_file(custom_jql, runtime_cfg=runtime_cfg).name),
            }
        )

    @app.get("/api/kanban")
    def api_kanban():
        assignee = request.args.get("assignee")
        priority = request.args.get("priority")
        keyword = request.args.get("q")
        custom_jql = request.args.get("jql")
        source_mode = request.args.get("source", "auto")
        cache_id = request.args.get("cache_id")
        period_mode = request.args.get("window", "weekly")
        period_start = request.args.get("start")
        period_end = request.args.get("end")
        debug_assignment = (request.args.get("debug_assignment") or "").strip().lower() == "true"

        try:
            cards, jql_preview, cache_meta = get_cards(
                assignee,
                priority,
                keyword,
                custom_jql,
                source_mode=source_mode,
                cache_id=cache_id,
            )
        except FileNotFoundError:
            return jsonify({"error": "No local query cache found. Call /api/query first."}), 409
        except JiraClientError as error:
            return jsonify({"error": str(error)}), 502

        runtime_cfg = get_runtime_config() or {}
        window = resolve_period_window(period_mode, period_start, period_end, cards=cards)
        manager_summary = build_manager_summary(cards, window, teams=runtime_cfg.get("teams") or [])

        historical_cards = build_historical_cards_for_window()
        current_keys = {str(card.get("key") or "") for card in cards}
        supplemental_cards = [
            card
            for card in historical_cards
            if str(card.get("key") or "") and str(card.get("key") or "") not in current_keys
        ]
        if supplemental_cards:
            history_summary = build_manager_summary(supplemental_cards, window, teams=runtime_cfg.get("teams") or [])
            manager_summary = merge_transfer_out_summary(manager_summary, history_summary)
            cards_summary = manager_summary.get("manager_summary_cards") or {}
            issue_total = int(cards_summary.get("transfer_out_issue_total", 0))
            event_total = int(cards_summary.get("transfer_out_event_total", 0))
            existing_text = str(manager_summary.get("manager_summary_text") or "")
            manager_summary["manager_summary_text"] = f"{existing_text}（含历史查询补偿后：评估后转出 {issue_total} 个问题/{event_total} 次流转）"

        columns = split_columns(cards)
        metrics = compute_member_metrics(cards, teams=runtime_cfg.get("teams") or [])
        assignees = sorted({card["assignee"] for card in cards})
        priorities = sorted({card["priority"] for card in cards})

        payload = {
            "columns": columns,
            "cards": cards,
            "metrics": metrics,
            "filters": {
                "assignees": assignees,
                "priorities": priorities,
            },
            "jql_preview": jql_preview,
            "cache_source": cache_meta.get("cache_source"),
            "cache_mode": cache_meta.get("cache_mode"),
            "cache_id": cache_meta.get("cache_id"),
            "cache_fallback": bool(cache_meta.get("cache_fallback", False)),
            **manager_summary,
        }
        if debug_assignment:
            payload["assignment_debug"] = build_assignment_debug(cards, window)

        return jsonify(payload)

    @app.get("/api/gantt")
    def api_gantt():
        mode = request.args.get("mode", "member")
        if mode not in {"member", "sprint"}:
            return jsonify({"error": "mode must be member or sprint"}), 400

        assignee = request.args.get("assignee")
        priority = request.args.get("priority")
        keyword = request.args.get("q")
        custom_jql = request.args.get("jql")
        source_mode = request.args.get("source", "auto")
        cache_id = request.args.get("cache_id")

        try:
            cards, jql_preview, cache_meta = get_cards(
                assignee,
                priority,
                keyword,
                custom_jql,
                source_mode=source_mode,
                cache_id=cache_id,
            )
        except FileNotFoundError:
            return jsonify({"error": "No local query cache found. Call /api/query first."}), 409
        except JiraClientError as error:
            return jsonify({"error": str(error)}), 502

        return jsonify(
            {
                "rows": build_gantt_rows(cards, mode=mode),
                "mode": mode,
                "jql_preview": jql_preview,
                "cache_source": cache_meta.get("cache_source"),
                "cache_mode": cache_meta.get("cache_mode"),
                "cache_id": cache_meta.get("cache_id"),
                "cache_fallback": bool(cache_meta.get("cache_fallback", False)),
            }
        )

    @app.get("/api/export/csv")
    def api_export_csv():
        try:
            cards, _, _ = get_cards(
                request.args.get("assignee"),
                request.args.get("priority"),
                request.args.get("q"),
                request.args.get("jql"),
            )
        except FileNotFoundError:
            return jsonify({"error": "No local query cache found. Call /api/query first."}), 409

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["key", "summary", "assignee", "priority", "status", "column", "created_at", "resolved_at", "url"])
        for card in cards:
            writer.writerow(
                [
                    card["key"],
                    card["summary"],
                    card["assignee"],
                    card["priority"],
                    card["status"],
                    card["column"],
                    card["timeline"].get("created_at"),
                    card["timeline"].get("resolved_at"),
                    card["url"],
                ]
            )

        buffer = BytesIO(output.getvalue().encode("utf-8"))
        return send_file(buffer, as_attachment=True, download_name="kanban_export.csv", mimetype="text/csv")

    @app.get("/api/export/xlsx")
    def api_export_xlsx():
        try:
            cards, _, _ = get_cards(
                request.args.get("assignee"),
                request.args.get("priority"),
                request.args.get("q"),
                request.args.get("jql"),
            )
        except FileNotFoundError:
            return jsonify({"error": "No local query cache found. Call /api/query first."}), 409
        metrics = compute_member_metrics(cards)

        workbook = Workbook()
        details = workbook.active
        details.title = "Details"
        details.append(["Key", "Summary", "Assignee", "Priority", "Status", "Column", "Created", "Resolved", "URL"])
        for card in cards:
            details.append(
                [
                    card["key"],
                    card["summary"],
                    card["assignee"],
                    card["priority"],
                    card["status"],
                    card["column"],
                    card["timeline"].get("created_at"),
                    card["timeline"].get("resolved_at"),
                    card["url"],
                ]
            )

        stats = workbook.create_sheet("Metrics")
        stats.append(["Assignee", "Total", "Resolved", "Resolution Rate", "WIP", "Avg Lead Time Hours", "Weighted Progress"])
        for row in metrics:
            stats.append(
                [
                    row["assignee"],
                    row["total"],
                    row["resolved"],
                    row["resolution_rate"],
                    row["wip"],
                    row["avg_lead_time_hours"],
                    row["weighted_progress"],
                ]
            )

        binary = BytesIO()
        workbook.save(binary)
        binary.seek(0)
        return send_file(
            binary,
            as_attachment=True,
            download_name="kanban_export.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/api/export/png")
    def api_export_png():
        mode = request.args.get("mode", "member")
        try:
            cards, _, _ = get_cards(
                request.args.get("assignee"),
                request.args.get("priority"),
                request.args.get("q"),
                request.args.get("jql"),
            )
        except FileNotFoundError:
            return jsonify({"error": "No local query cache found. Call /api/query first."}), 409
        rows = build_gantt_rows(cards, mode=mode)

        lanes = sorted({row["lane"] for row in rows})
        lane_index = {lane: index for index, lane in enumerate(lanes)}

        fig, ax = plt.subplots(figsize=(12, 5 if lanes else 2))
        for row in rows:
            y = lane_index[row["lane"]]
            start = row["start"]
            end = row["end"]
            ax.plot([start, end], [y, y], linewidth=8)

        ax.set_yticks(range(len(lanes)))
        ax.set_yticklabels(lanes)
        ax.set_title("Gantt Snapshot")
        ax.set_xlabel("Time")

        image = BytesIO()
        fig.tight_layout()
        fig.savefig(image, format="png")
        plt.close(fig)
        image.seek(0)
        return send_file(image, as_attachment=True, download_name="gantt_export.png", mimetype="image/png")

    return app


def _bootstrap_default_app() -> Flask:
    try:
        return create_app()
    except Exception as error:
        fallback = Flask(__name__)
        error_message = f"Configuration required before startup: {error}"

        @fallback.get("/")
        def config_error():
            return jsonify({"error": error_message}), 500

        return fallback


app = _bootstrap_default_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
