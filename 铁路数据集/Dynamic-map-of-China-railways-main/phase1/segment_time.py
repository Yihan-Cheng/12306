"""
Repair and derive segment time fields from 发车/到达 text cells.

Used by: anomaly analysis, trains_segments CSV repair, prepare_simulation_data.
"""

from __future__ import annotations

from typing import Any, Optional

from phase1.time_utils import parse_time_text


def recompute_segment_times_from_strings(row: dict[str, Any]) -> dict[str, Any] | None:
    """
    Recompute all numeric time columns from segment_depart_time_str / segment_arrive_time_str.

    Returns a dict of updated CSV fields, or None if times cannot be parsed.
    Sets segment_duration_minutes = arr_total - dep_total (always >= 1 when successful).
    """
    dep_s = (row.get("segment_depart_time_str") or "").strip()
    arr_s = (row.get("segment_arrive_time_str") or "").strip()
    p1 = parse_time_text(dep_s) if dep_s else None
    p2 = parse_time_text(arr_s) if arr_s else None
    if not p1 or not p2:
        return None

    dep_total = p1.minute_total
    dur = p2.minute_total - p1.minute_total

    if dur <= 0 and p1.day_offset == 0 and p2.day_offset == 0 and p2.minute_of_day < p1.minute_of_day:
        # 两格都标「当日」但到达钟点早于出发 — 视为跨日未标
        dur = p2.minute_of_day + 1440 - p1.minute_of_day

    if dur <= 0:
        return None

    arr_total = dep_total + dur

    dep_day = dep_total // 1440
    dep_mod = dep_total % 1440
    arr_day = arr_total // 1440
    arr_mod = arr_total % 1440

    return {
        "segment_depart_minute_of_day": dep_mod,
        "segment_arrive_minute_of_day": arr_mod,
        "segment_depart_day_offset": dep_day,
        "segment_arrive_day_offset": arr_day,
        "segment_depart_minute_total": dep_total,
        "segment_arrive_minute_total": arr_total,
        "segment_duration_minutes": dur,
    }


def effective_duration_minutes(row: dict[str, Any]) -> tuple[Optional[float], str]:
    """
    Duration in minutes for speed checks; prefers recomputed segment fields.
    """
    fixed = recompute_segment_times_from_strings(row)
    if fixed is not None:
        return float(fixed["segment_duration_minutes"]), "reparsed"
    try:
        stored = float(row.get("segment_duration_minutes") or "")
        if stored > 0:
            return stored, "stored_only"
    except ValueError:
        pass
    return None, "none"


def implied_speed_kmh(dist_m: float, duration_min: float) -> float:
    if duration_min <= 0:
        return float("inf")
    dist_km = dist_m / 1000.0
    return dist_km / (duration_min / 60.0)
