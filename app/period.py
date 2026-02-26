from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .normalize import parse_datetime


def _start_of_week(now: datetime) -> datetime:
    return now - timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)


def resolve_period_window(
    mode: str | None,
    start: str | None,
    end: str | None,
    cards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_mode = (mode or "weekly").strip().lower()
    now = datetime.now().astimezone()

    parsed_start = parse_datetime(start)
    parsed_end = parse_datetime(end)
    if parsed_start and parsed_end and parsed_start < parsed_end:
        return {
            "mode": "custom",
            "label": "自定义区间",
            "start": parsed_start,
            "end": parsed_end,
            "timezone": str(parsed_start.tzinfo or now.tzinfo or "local"),
        }

    if normalized_mode == "rolling_7d":
        return {
            "mode": "rolling_7d",
            "label": "最近7天",
            "start": now - timedelta(days=7),
            "end": now,
            "timezone": str(now.tzinfo or "local"),
        }

    if normalized_mode == "sprint":
        if cards:
            points: list[datetime] = []
            for card in cards:
                timeline = card.get("timeline", {}) or {}
                for key in ("created_at", "developer_started_at", "resolved_at"):
                    point = parse_datetime(timeline.get(key))
                    if point:
                        points.append(point)
            if points:
                return {
                    "mode": "sprint",
                    "label": "当前Sprint",
                    "start": min(points),
                    "end": max(points),
                    "timezone": str((min(points).tzinfo or now.tzinfo or "local")),
                }

        return {
            "mode": "sprint",
            "label": "当前Sprint",
            "start": now - timedelta(days=14),
            "end": now,
            "timezone": str(now.tzinfo or "local"),
        }

    start_of_week = _start_of_week(now)
    return {
        "mode": "weekly",
        "label": "本周",
        "start": start_of_week,
        "end": start_of_week + timedelta(days=7),
        "timezone": str(now.tzinfo or "local"),
    }
