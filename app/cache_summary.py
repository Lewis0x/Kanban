"""从已归一化的卡片列表生成「按任务负责人」汇总（便于对照缓存快速定位问题）。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _owner_key(card: dict[str, Any]) -> str:
    name = (card.get("metric_owner") or "").strip()
    return name if name else "未分配"


def summarize_by_metric_owner(cards: list[dict[str, Any]]) -> dict[str, Any]:
    """按 metric_owner 分组；组内 issue 按 key 排序。"""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        groups[_owner_key(card)].append(card)

    for owner in groups:
        groups[owner].sort(key=lambda c: (c.get("key") or ""))

    # 负责人按名下 issue 数降序，再按名称
    ordered = dict(
        sorted(
            groups.items(),
            key=lambda item: (-len(item[1]), item[0].lower() if item[0] != "未分配" else "zzz"),
        )
    )
    return {
        "total_issues": len(cards),
        "by_owner": ordered,
        "owner_counts": {k: len(v) for k, v in ordered.items()},
    }


def task_owner_provenance_note(row: dict[str, Any]) -> str:
    """根据 task_owner_source 生成中文来源说明（供文本报告与人工核对）。"""
    src = row.get("task_owner_source")
    to = row.get("task_owner")
    fid = row.get("task_owner_jira_field")
    mo = (row.get("metric_owner") or "").strip()
    if src == "jira_field":
        ff = fid or "?"
        return f"task_owner={to} 来源=Jira自定义字段 fields[{ff}]"
    if src == "changelog":
        return f"task_owner={to} 来源=issue.changelog（按时间最后一次「Task Owner」或「任务负责人」）"
    if to:
        return f"task_owner={to}"
    return f"task_owner=(无)  metric_owner={mo or '未分配'} 来源=经办人+角色规则推导（无字段快照且无有效 changelog）"


def issue_detail_line(card: dict[str, Any], *, max_summary_len: int = 80) -> dict[str, Any]:
    """单条 issue 的结构化摘要（用于 JSON 或表格列）。"""
    summary = (card.get("summary") or "").replace("\r", " ").replace("\n", " ").strip()
    if len(summary) > max_summary_len:
        summary = summary[: max_summary_len - 1] + "…"
    return {
        "key": card.get("key"),
        "summary": summary,
        "status": card.get("status"),
        "column": card.get("column"),
        "assignee": card.get("assignee"),
        "task_owner": card.get("task_owner"),
        "task_owner_source": card.get("task_owner_source"),
        "task_owner_jira_field": card.get("task_owner_jira_field"),
        "metric_owner": card.get("metric_owner"),
        "priority": card.get("priority"),
        "issue_type": card.get("issue_type"),
        "url": card.get("url"),
        "task_owner_provenance": task_owner_provenance_note(
            {
                "task_owner_source": card.get("task_owner_source"),
                "task_owner": card.get("task_owner"),
                "task_owner_jira_field": card.get("task_owner_jira_field"),
                "metric_owner": card.get("metric_owner"),
            }
        ),
    }


def build_summary_payload(
    cards: list[dict[str, Any]],
    *,
    meta: dict[str, Any] | None = None,
    max_summary_len: int = 80,
) -> dict[str, Any]:
    """生成可 JSON 序列化的完整汇总。"""
    summary = summarize_by_metric_owner(cards)
    detail_by_owner: dict[str, list[dict[str, Any]]] = {}
    for owner, items in summary["by_owner"].items():
        detail_by_owner[owner] = [issue_detail_line(c, max_summary_len=max_summary_len) for c in items]
    out: dict[str, Any] = {
        "total_issues": summary["total_issues"],
        "owner_counts": summary["owner_counts"],
        "by_owner": detail_by_owner,
    }
    if meta:
        out["meta"] = meta
    return out


def format_text_report(payload: dict[str, Any]) -> str:
    """人类可读的纯文本报告（适合复制到 IM / 工单）。"""
    lines: list[str] = []
    meta = payload.get("meta") or {}
    if meta.get("cache_file"):
        lines.append(f"缓存文件: {meta['cache_file']}")
    if meta.get("jql_preview"):
        lines.append(f"JQL 预览: {meta['jql_preview']}")
    if meta.get("issue_count_cache") is not None:
        lines.append(f"缓存内 issue_count 字段: {meta['issue_count_cache']}")
    lines.append(f"当前汇总 Issue 总数: {payload['total_issues']}")
    lines.append("")
    lines.append("说明: 每条下的「task_owner / metric_owner 来源」与看板 normalize_issue 一致（Jira 字段 > changelog > 推导）。")
    lines.append("")
    lines.append("=== 按任务负责人 (metric_owner) ===")
    lines.append("")

    for owner, rows in payload["by_owner"].items():
        n = len(rows)
        lines.append(f"【{owner}】 共 {n} 条")
        lines.append("-" * 72)
        for r in rows:
            key = r.get("key") or ""
            st = r.get("status") or ""
            col = r.get("column") or ""
            asn = r.get("assignee") or ""
            pr = r.get("priority") or ""
            summ = r.get("summary") or ""
            prov = r.get("task_owner_provenance") or task_owner_provenance_note(r)
            lines.append(f"  {key}\t{st}\t{col}\t经办:{asn}\t{pr}")
            lines.append(f"    {prov}")
            lines.append(f"    {summ}")
            if r.get("url"):
                lines.append(f"    {r['url']}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
