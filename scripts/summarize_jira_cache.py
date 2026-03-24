#!/usr/bin/env python3
"""
从本地 Jira 查询缓存汇总：Issue 总数 + 按任务负责人 (metric_owner) 分组的明细。

用法（在 Kanban 项目根目录）:
  .\\.venv\\Scripts\\python.exe scripts\\summarize_jira_cache.py
  .\\.venv\\Scripts\\python.exe scripts\\summarize_jira_cache.py --cache-id <64位hex>
  .\\.venv\\Scripts\\python.exe scripts\\summarize_jira_cache.py --json --out summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 包根目录 = 本脚本上级
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.cache_summary import build_summary_payload, format_text_report
from app.config import load_config, normalize_task_owner_field_id
from app.normalize import normalize_issue


def _latest_cache_file(cache_dir: Path) -> Path | None:
    files = [p for p in cache_dir.glob("*.json") if p.is_file()]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _load_payload(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize Jira query cache by metric_owner (task owner on board).")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to jira_auth.yaml (default: config/jira_auth.yaml next to app)",
    )
    parser.add_argument("--cache-id", type=str, default=None, help="64-char cache file stem (sha256 hex)")
    parser.add_argument(
        "--cache-file",
        type=str,
        default=None,
        help="Absolute or relative path to a cache JSON file",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    parser.add_argument("--out", type=str, default=None, help="Write output to this file (UTF-8)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    base_url = (cfg.get("base_url") or "").rstrip("/") or "https://jira.local"
    status_mapping = cfg.get("status_mapping")
    role_settings = cfg.get("role_settings")
    task_owner_field = normalize_task_owner_field_id(cfg.get("task_owner_field"))

    cache_dir = ROOT / "storage" / "jira_query_cache"
    cache_path: Path | None = None
    if args.cache_file:
        cache_path = Path(args.cache_file).resolve()
        if not cache_path.is_file():
            print(f"[error] cache file not found: {cache_path}", file=sys.stderr)
            return 1
    elif args.cache_id:
        stem = args.cache_id.strip().lower()
        if len(stem) != 64 or any(c not in "0123456789abcdef" for c in stem):
            print("[error] --cache-id must be 64 hex characters", file=sys.stderr)
            return 1
        cache_path = cache_dir / f"{stem}.json"
        if not cache_path.is_file():
            print(f"[error] cache not found: {cache_path}", file=sys.stderr)
            return 1
    else:
        cache_path = _latest_cache_file(cache_dir)
        if cache_path is None:
            print(f"[error] no JSON caches under {cache_dir}", file=sys.stderr)
            return 1

    payload_raw = _load_payload(cache_path)
    issues = payload_raw.get("issues") or []
    cards = [
        normalize_issue(
            issue,
            base_url=base_url,
            status_mapping=status_mapping,
            role_settings=role_settings,
            task_owner_field=task_owner_field,
        )
        for issue in issues
    ]

    try:
        cache_rel = str(cache_path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        cache_rel = str(cache_path.resolve())
    meta = {
        "cache_file": cache_rel,
        "jql_preview": payload_raw.get("jql_preview"),
        "issue_count_cache": payload_raw.get("issue_count"),
        "normalized_count": len(cards),
    }
    summary = build_summary_payload(cards, meta=meta)

    if args.json:
        text = json.dumps(summary, ensure_ascii=False, indent=2)
    else:
        text = format_text_report(summary)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
