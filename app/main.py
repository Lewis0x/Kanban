from __future__ import annotations

import csv
import hashlib
import json
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, send_file
from matplotlib import pyplot as plt
from openpyxl import Workbook

from .config import load_config
from .jira_client import JiraClient, JiraClientError, JiraConfig
from .analytics import build_manager_summary
from .metrics import build_gantt_rows, compute_member_metrics
from .normalize import filter_cards, normalize_issue, split_columns
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

    def get_latest_cache_file() -> Path | None:
        files = [path for path in cache_dir.glob("*.json") if path.is_file()]
        if not files:
            return None
        return max(files, key=lambda path: path.stat().st_mtime)

    def get_cache_file_by_id(cache_id: str | None) -> Path | None:
        normalized = (cache_id or "").strip().lower()
        if len(normalized) != 64 or any(ch not in "0123456789abcdef" for ch in normalized):
            return None
        path = cache_dir / f"{normalized}.json"
        if not path.exists() or not path.is_file():
            return None
        return path

    def load_cache_payload(cache_file: Path) -> dict[str, Any]:
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FileNotFoundError("Query cache not found") from exc

    def query_and_cache_issues(custom_jql: str | None, runtime_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
        runtime_client = get_runtime_client(runtime_cfg)
        issues = runtime_client.get_issues_by_jql(jql=custom_jql)
        payload = {
            "custom_jql": custom_jql,
            "jql_preview": build_jql_preview(custom_jql, runtime_cfg=runtime_cfg),
            "issue_count": len(issues),
            "issues": issues,
        }
        cache_file = get_cache_file(custom_jql, runtime_cfg=runtime_cfg)
        cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    def load_cached_issues(
        custom_jql: str | None,
        runtime_cfg: dict[str, Any] | None = None,
        source: str = "auto",
        cache_id: str | None = None,
    ) -> tuple[dict[str, Any], Path, bool]:
        requested_cache_file = get_cache_file(custom_jql, runtime_cfg=runtime_cfg)
        cache_file = requested_cache_file
        fallback_used = False
        source_mode = (source or "auto").strip().lower()

        if source_mode == "requested":
            if not requested_cache_file.exists():
                raise FileNotFoundError("Query cache not found")
            cache_file = requested_cache_file
        elif source_mode == "latest":
            latest_cache_file = get_latest_cache_file()
            if latest_cache_file is None:
                raise FileNotFoundError("Query cache not found")
            cache_file = latest_cache_file
            fallback_used = latest_cache_file != requested_cache_file
        elif source_mode == "cache_id":
            selected_cache_file = get_cache_file_by_id(cache_id)
            if selected_cache_file is None:
                raise FileNotFoundError("Query cache not found")
            cache_file = selected_cache_file
            fallback_used = selected_cache_file != requested_cache_file
        else:
            if not requested_cache_file.exists():
                latest_cache_file = get_latest_cache_file()
                if latest_cache_file is None:
                    raise FileNotFoundError("Query cache not found")
                cache_file = latest_cache_file
                fallback_used = True

        return load_cache_payload(cache_file), cache_file, fallback_used

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

    def list_all_cache_sources() -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for cache_file in cache_dir.glob("*.json"):
            try:
                payload = load_cache_payload(cache_file)
            except FileNotFoundError:
                continue
            entries.append(
                {
                    "id": cache_file.stem,
                    "issue_count": int(payload.get("issue_count", 0)),
                    "jql_preview": str(payload.get("jql_preview", "")),
                    "custom_jql": str(payload.get("custom_jql", "") or ""),
                    "updated_at": cache_file.stat().st_mtime,
                }
            )
        return sorted(entries, key=lambda row: row["updated_at"], reverse=True)

    def get_cards(
        assignee: str | None,
        priority: str | None,
        keyword: str | None,
        custom_jql: str | None,
        source: str = "auto",
        cache_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str, str, bool]:
        runtime_cfg = get_runtime_config()
        payload, cache_file, fallback_used = load_cached_issues(
            custom_jql,
            runtime_cfg=runtime_cfg,
            source=source,
            cache_id=cache_id,
        )
        issues = payload.get("issues", [])
        base_url = (runtime_cfg or {}).get("base_url") or "https://jira.local"
        status_mapping = (runtime_cfg or {}).get("status_mapping")
        role_settings = (runtime_cfg or {}).get("role_settings")
        cards = [
            normalize_issue(issue, base_url=base_url, status_mapping=status_mapping, role_settings=role_settings)
            for issue in issues
        ]
        cache_source = str(cache_file.relative_to(Path(__file__).resolve().parent.parent)).replace("\\", "/")
        return (
            filter_cards(cards, assignee=assignee, priority=priority, keyword=keyword),
            str(payload.get("jql_preview", "")),
            cache_source,
            fallback_used,
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
        return jsonify({"sources": list_all_cache_sources()})

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
        source = request.args.get("source", "auto")
        cache_id = request.args.get("cache_id")
        window_mode = request.args.get("window", "weekly")
        window_start = request.args.get("start")
        window_end = request.args.get("end")

        try:
            cards, jql_preview, cache_source, cache_fallback = get_cards(
                assignee,
                priority,
                keyword,
                custom_jql,
                source=source,
                cache_id=cache_id,
            )
        except FileNotFoundError:
            return jsonify({"error": "No local query cache found. Call /api/query first."}), 409
        except JiraClientError as error:
            return jsonify({"error": str(error)}), 502

        columns = split_columns(cards)
        metrics = compute_member_metrics(cards)
        window = resolve_period_window(window_mode, window_start, window_end, cards=cards)
        summary = build_manager_summary(cards, window)
        assignees = sorted({card["assignee"] for card in cards})
        priorities = sorted({card["priority"] for card in cards})

        return jsonify(
            {
                "columns": columns,
                "cards": cards,
                "metrics": metrics,
                "filters": {
                    "assignees": assignees,
                    "priorities": priorities,
                },
                "jql_preview": jql_preview,
                "cache_source": cache_source,
                "cache_fallback": cache_fallback,
                "cache_mode": source,
                "cache_id": cache_id,
                "summary_window": summary["summary_window"],
                "manager_summary_cards": summary["manager_summary_cards"],
                "manager_summary_text": summary["manager_summary_text"],
                "period_focus": summary["period_focus"],
            }
        )

    @app.get("/api/gantt")
    def api_gantt():
        mode = request.args.get("mode", "member")
        if mode not in {"member", "sprint"}:
            return jsonify({"error": "mode must be member or sprint"}), 400

        assignee = request.args.get("assignee")
        priority = request.args.get("priority")
        keyword = request.args.get("q")
        custom_jql = request.args.get("jql")
        source = request.args.get("source", "auto")
        cache_id = request.args.get("cache_id")

        try:
            cards, jql_preview, cache_source, cache_fallback = get_cards(
                assignee,
                priority,
                keyword,
                custom_jql,
                source=source,
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
                "cache_source": cache_source,
                "cache_fallback": cache_fallback,
                "cache_mode": source,
                "cache_id": cache_id,
            }
        )

    @app.get("/api/export/csv")
    def api_export_csv():
        source = request.args.get("source", "auto")
        cache_id = request.args.get("cache_id")
        try:
            cards, _, _, _ = get_cards(
                request.args.get("assignee"),
                request.args.get("priority"),
                request.args.get("q"),
                request.args.get("jql"),
                source=source,
                cache_id=cache_id,
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
        source = request.args.get("source", "auto")
        cache_id = request.args.get("cache_id")
        try:
            cards, _, _, _ = get_cards(
                request.args.get("assignee"),
                request.args.get("priority"),
                request.args.get("q"),
                request.args.get("jql"),
                source=source,
                cache_id=cache_id,
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
        source = request.args.get("source", "auto")
        cache_id = request.args.get("cache_id")
        try:
            cards, _, _, _ = get_cards(
                request.args.get("assignee"),
                request.args.get("priority"),
                request.args.get("q"),
                request.args.get("jql"),
                source=source,
                cache_id=cache_id,
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
