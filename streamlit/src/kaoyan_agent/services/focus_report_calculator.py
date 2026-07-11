from __future__ import annotations

from typing import Any, Dict, Iterable

from kaoyan_agent.schemas.focus import FocusReportOutput
from kaoyan_agent.services.focus_temporal_tracker import DETECTOR_VERSION


NARRATIVE_FIELDS = ("ai_summary", "possible_problem_signal", "suggested_action")


def calculate_focus_report(
    session: Dict[str, Any],
    state_events: Iterable[Dict[str, Any]],
    narrative: Dict[str, Any] | None = None,
    *,
    minimum_coverage: float = 0.8,
) -> Dict[str, Any]:
    events = list(state_events)
    durations = {"focused": 0, "distracted": 0, "away": 0, "unknown": 0}
    blocked_count = 0
    distracted_count = 0
    away_count = 0
    previous_state = ""
    longest_focus_seconds = 0
    current_focus_seconds = 0

    for event in events:
        state = str(event.get("state_type") or "unknown")
        seconds = max(0, _int(event.get("observed_seconds"), 0))
        normalized_state = state if state in durations else "unknown"
        if state == "blocked":
            blocked_count += 1
        durations[normalized_state] += seconds
        if state == "distracted" and previous_state != "distracted":
            distracted_count += 1
        if state == "away" and previous_state != "away":
            away_count += 1
        if state == "focused":
            current_focus_seconds += seconds
            longest_focus_seconds = max(longest_focus_seconds, current_focus_seconds)
        else:
            current_focus_seconds = 0
        previous_state = state

    monitored_seconds = sum(durations.values())
    classified_seconds = durations["focused"] + durations["distracted"] + durations["away"]
    session_seconds = max(
        0,
        _int(session.get("actual_seconds"), 0)
        or _int(session.get("actual_minutes"), 0) * 60,
    )
    coverage_ratio = min(1.0, monitored_seconds / session_seconds) if session_seconds else 0.0
    classified_ratio = classified_seconds / monitored_seconds if monitored_seconds else 0.0
    focus_score = round(100 * durations["focused"] / classified_seconds) if classified_seconds else 0
    sufficient = coverage_ratio >= minimum_coverage and classified_ratio >= minimum_coverage
    evidence_status = "sufficient" if sufficient else "insufficient"
    if not sufficient:
        quality = "evidence_insufficient"
    elif focus_score >= 80:
        quality = "stable"
    elif focus_score >= 60:
        quality = "mixed"
    else:
        quality = "unstable"

    default_narrative = {
        "ai_summary": (
            f"本次共获得 {monitored_seconds} 秒有效监测，"
            f"其中专注 {durations['focused']} 秒、分心 {durations['distracted']} 秒、"
            f"离开 {durations['away']} 秒、无法判断 {durations['unknown']} 秒。"
        ),
        "possible_problem_signal": (
            "监测覆盖不足，当前视觉证据不能代表整场学习。"
            if not sufficient
            else "当前指标未发现需要单独升级的问题线索。"
        ),
        "suggested_action": "保持摄像头覆盖完整专注时段，并结合任务完成情况复盘。",
    }
    if sufficient:
        narrative = narrative or {}
        for field in NARRATIVE_FIELDS:
            value = str(narrative.get(field) or "").strip()
            if value:
                default_narrative[field] = value

    payload = {
        "focus_score": focus_score,
        "effective_focus_minutes": round(durations["focused"] / 60),
        "away_count": away_count,
        "distracted_count": distracted_count,
        "blocked_count": blocked_count,
        "longest_focus_minutes": round(longest_focus_seconds / 60),
        "focus_quality": quality,
        **default_narrative,
        "monitored_seconds": monitored_seconds,
        "coverage_ratio": round(coverage_ratio, 4),
        "classified_ratio": round(classified_ratio, 4),
        "focused_seconds": durations["focused"],
        "distracted_seconds": durations["distracted"],
        "away_seconds": durations["away"],
        "unknown_seconds": durations["unknown"],
        "evidence_status": evidence_status,
        "detector_version": DETECTOR_VERSION,
    }
    return FocusReportOutput.model_validate(payload).model_dump()


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
