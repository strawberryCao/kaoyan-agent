from contextlib import closing
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import get_connection, int_value, json_dumps, rows_to_dicts, utc_now


class FocusRepository:
    def create_session(
        self,
        task_id: Optional[int],
        planned_minutes: int,
        task_title: str = "",
        subject: str = "",
        started_at: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> int:
        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO focus_sessions (
                    project_id,
                    task_id,
                    task_title,
                    subject,
                    planned_minutes,
                    timer_status,
                    segment_started_at,
                    accumulated_seconds,
                    actual_seconds,
                    started_at,
                    completion_status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'running', ?, 0, 0, ?, 'running', ?, ?)
                """,
                (
                    project_id,
                    task_id,
                    task_title.strip(),
                    subject.strip(),
                    planned_minutes,
                    started_at or now,
                    started_at or now,
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def record_timeline_event(
        self,
        focus_session_id: int,
        event_type: str,
        note: str = "",
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO focus_timeline_events (
                    focus_session_id,
                    event_type,
                    note,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (focus_session_id, event_type, note, utc_now()),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def record_state_event(
        self,
        focus_session_id: int,
        state_type: str,
        confidence: float = 0.0,
        focus_score: int = 0,
        explanation: str = "",
        observed_seconds: int = 0,
        detector_version: str = "legacy_unverified",
    ) -> int:
        if state_type not in {"focused", "away", "distracted", "blocked", "unknown"}:
            state_type = "unknown"
        focus_score = max(0, min(100, int_value(focus_score, 0)))
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO focus_state_events (
                    focus_session_id,
                    state_type,
                    confidence,
                    focus_score,
                    observed_seconds,
                    detector_version,
                    explanation,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    focus_session_id,
                    state_type,
                    confidence,
                    focus_score,
                    max(0, int_value(observed_seconds, 0)),
                    str(detector_version or "legacy_unverified"),
                    explanation,
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def get_session(self, focus_session_id: int) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    project_id,
                    task_id,
                    task_title,
                    subject,
                    planned_minutes,
                    timer_status,
                    segment_started_at,
                    accumulated_seconds,
                    actual_seconds,
                    actual_minutes,
                    pause_count,
                    completion_status,
                    reflection,
                    started_at,
                    ended_at,
                    created_at,
                    updated_at
                FROM focus_sessions
                WHERE id = ?
                """,
                (focus_session_id,),
            ).fetchone()
        return self.normalize_session(row) if row else None

    def get_active_timer_session(
        self,
        project_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        params: list[Any] = []
        project_clause = ""
        if project_id is not None:
            project_clause = "AND project_id = ?"
            params.append(project_id)
        with closing(get_connection()) as connection:
            row = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    task_id,
                    task_title,
                    subject,
                    planned_minutes,
                    timer_status,
                    segment_started_at,
                    accumulated_seconds,
                    actual_seconds,
                    actual_minutes,
                    pause_count,
                    completion_status,
                    reflection,
                    started_at,
                    ended_at,
                    created_at,
                    updated_at
                FROM focus_sessions
                WHERE ended_at IS NULL
                  AND timer_status IN ('running', 'paused')
                  {project_clause}
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        return self.normalize_session(row) if row else None

    def update_timer_state(
        self,
        focus_session_id: int,
        *,
        timer_status: str,
        accumulated_seconds: int,
        pause_count: int,
        segment_started_at: Optional[str] = None,
        completion_status: Optional[str] = None,
    ) -> bool:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE focus_sessions
                SET
                    timer_status = ?,
                    accumulated_seconds = ?,
                    actual_seconds = ?,
                    pause_count = ?,
                    segment_started_at = ?,
                    completion_status = COALESCE(?, completion_status),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    timer_status,
                    max(0, int_value(accumulated_seconds, 0)),
                    max(0, int_value(accumulated_seconds, 0)),
                    max(0, int_value(pause_count, 0)),
                    segment_started_at or "",
                    completion_status,
                    utc_now(),
                    focus_session_id,
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

    def list_state_events(self, focus_session_id: int) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    focus_session_id,
                    state_type,
                    confidence,
                    focus_score,
                    observed_seconds,
                    detector_version,
                    explanation,
                    created_at
                FROM focus_state_events
                WHERE focus_session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (focus_session_id,),
            ).fetchall()
        return rows_to_dicts(rows)

    def get_latest_state_event(self, focus_session_id: int) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    focus_session_id,
                    state_type,
                    confidence,
                    focus_score,
                    observed_seconds,
                    detector_version,
                    explanation,
                    created_at
                FROM focus_state_events
                WHERE focus_session_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (focus_session_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_timeline_events(self, focus_session_id: int) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    focus_session_id,
                    event_type,
                    note,
                    created_at
                FROM focus_timeline_events
                WHERE focus_session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (focus_session_id,),
            ).fetchall()
        return rows_to_dicts(rows)

    def finish_session(
        self,
        focus_session_id: int,
        actual_minutes: int,
        pause_count: int,
        completion_status: str,
        reflection: str = "",
        ended_at: Optional[str] = None,
        actual_seconds: Optional[int] = None,
    ) -> bool:
        now = utc_now()
        saved_actual_seconds = (
            max(0, int_value(actual_seconds, 0))
            if actual_seconds is not None
            else max(0, int_value(actual_minutes, 0) * 60)
        )
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE focus_sessions
                SET
                    timer_status = 'ended',
                    segment_started_at = '',
                    accumulated_seconds = ?,
                    actual_minutes = ?,
                    actual_seconds = ?,
                    pause_count = ?,
                    completion_status = ?,
                    reflection = ?,
                    ended_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    saved_actual_seconds,
                    actual_minutes,
                    saved_actual_seconds,
                    pause_count,
                    completion_status,
                    reflection,
                    ended_at or now,
                    now,
                    focus_session_id,
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

    def list_recent_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    project_id,
                    task_id,
                    task_title,
                    subject,
                    planned_minutes,
                    timer_status,
                    segment_started_at,
                    accumulated_seconds,
                    actual_seconds,
                    actual_minutes,
                    pause_count,
                    completion_status,
                    reflection,
                    started_at,
                    ended_at,
                    created_at,
                    updated_at
                FROM focus_sessions
                WHERE ended_at IS NOT NULL
                ORDER BY ended_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, int_value(limit, 20)),),
            ).fetchall()
        return [self.normalize_session(row) for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        today = date.today().isoformat()
        week_start = (date.today() - timedelta(days=6)).isoformat()

        with closing(get_connection()) as connection:
            today_rows = connection.execute(
                """
                SELECT actual_seconds, actual_minutes, completion_status
                FROM focus_sessions
                WHERE ended_at IS NOT NULL
                  AND date(started_at) = ?
                """,
                (today,),
            ).fetchall()
            week_rows = connection.execute(
                """
                SELECT actual_seconds, actual_minutes, completion_status
                FROM focus_sessions
                WHERE ended_at IS NOT NULL
                  AND date(started_at) >= ?
                """,
                (week_start,),
            ).fetchall()
            total_rows = connection.execute(
                """
                SELECT actual_seconds, actual_minutes, completion_status
                FROM focus_sessions
                WHERE ended_at IS NOT NULL
                """
            ).fetchall()
            daily_rows = connection.execute(
                """
                SELECT
                    date(started_at) AS day,
                    SUM(CASE WHEN actual_seconds > 0 THEN actual_seconds ELSE actual_minutes * 60 END) AS total_seconds
                FROM focus_sessions
                WHERE ended_at IS NOT NULL
                  AND date(started_at) >= ?
                GROUP BY date(started_at)
                ORDER BY day ASC
                """,
                (week_start,),
            ).fetchall()

        def summarize(rows):
            sessions = len(rows)
            total_seconds = sum(self.actual_seconds_from_row(row) for row in rows)
            minutes = round(total_seconds / 60, 1)
            completed = sum(
                1 for row in rows if str(row["completion_status"]) == "completed"
            )
            return sessions, minutes, completed

        today_sessions, today_focus_minutes, today_completed = summarize(today_rows)
        week_sessions, week_focus_minutes, week_completed = summarize(week_rows)
        total_sessions, total_focus_minutes, total_completed = summarize(total_rows)
        completion_rate = (
            round(total_completed / total_sessions * 100, 1)
            if total_sessions
            else 0.0
        )

        return {
            "today_sessions": today_sessions,
            "today_focus_minutes": today_focus_minutes,
            "today_completed": today_completed,
            "week_sessions": week_sessions,
            "week_focus_minutes": week_focus_minutes,
            "week_completed": week_completed,
            "total_sessions": total_sessions,
            "total_focus_minutes": total_focus_minutes,
            "completion_rate": completion_rate,
            "daily_minutes": {
                row["day"]: round(int_value(row["total_seconds"], 0) / 60, 1)
                for row in daily_rows
            },
        }

    @staticmethod
    def actual_seconds_from_row(row) -> int:
        accumulated_seconds = int_value(row["accumulated_seconds"], 0) if "accumulated_seconds" in row.keys() else 0
        if accumulated_seconds > 0:
            return accumulated_seconds
        actual_seconds = int_value(row["actual_seconds"], 0)
        if actual_seconds > 0:
            return actual_seconds
        return int_value(row["actual_minutes"], 0) * 60

    @classmethod
    def normalize_session(cls, row) -> Dict[str, Any]:
        data = dict(row)
        data["actual_seconds"] = cls.actual_seconds_from_row(row)
        data["timer_status"] = str(data.get("timer_status") or "ended")
        data["accumulated_seconds"] = int_value(data.get("accumulated_seconds"), 0)
        data["completed"] = str(data.get("completion_status") or "") == "completed"
        return data

    def create_report(
        self,
        focus_session_id: int,
        report: Dict[str, Any],
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO focus_reports (
                    focus_session_id,
                    focus_score,
                    effective_focus_minutes,
                    away_count,
                    distracted_count,
                    blocked_count,
                    longest_focus_minutes,
                    focus_quality,
                    ai_summary,
                    possible_problem_signal,
                    suggested_action,
                    monitored_seconds,
                    coverage_ratio,
                    classified_ratio,
                    focused_seconds,
                    distracted_seconds,
                    away_seconds,
                    unknown_seconds,
                    evidence_status,
                    detector_version,
                    raw_result_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    focus_session_id,
                    int(report.get("focus_score") or 0),
                    int(report.get("effective_focus_minutes") or 0),
                    int(report.get("away_count") or 0),
                    int(report.get("distracted_count") or 0),
                    int(report.get("blocked_count") or 0),
                    int(report.get("longest_focus_minutes") or 0),
                    str(report.get("focus_quality") or ""),
                    str(report.get("ai_summary") or ""),
                    str(report.get("possible_problem_signal") or ""),
                    str(report.get("suggested_action") or ""),
                    int(report.get("monitored_seconds") or 0),
                    float(report.get("coverage_ratio") or 0.0),
                    float(report.get("classified_ratio") or 0.0),
                    int(report.get("focused_seconds") or 0),
                    int(report.get("distracted_seconds") or 0),
                    int(report.get("away_seconds") or 0),
                    int(report.get("unknown_seconds") or 0),
                    str(report.get("evidence_status") or "insufficient"),
                    str(report.get("detector_version") or "zero_label_evidence_v1"),
                    json_dumps(report, {}),
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def get_report(self, report_id: int) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    focus_session_id,
                    focus_score,
                    effective_focus_minutes,
                    away_count,
                    distracted_count,
                    blocked_count,
                    longest_focus_minutes,
                    focus_quality,
                    ai_summary,
                    possible_problem_signal,
                    suggested_action,
                    monitored_seconds,
                    coverage_ratio,
                    classified_ratio,
                    focused_seconds,
                    distracted_seconds,
                    away_seconds,
                    unknown_seconds,
                    evidence_status,
                    detector_version,
                    raw_result_json,
                    created_at
                FROM focus_reports
                WHERE id = ?
                """,
                (report_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    focus_session_id,
                    focus_score,
                    effective_focus_minutes,
                    away_count,
                    distracted_count,
                    blocked_count,
                    longest_focus_minutes,
                    focus_quality,
                    ai_summary,
                    possible_problem_signal,
                    suggested_action,
                    monitored_seconds,
                    coverage_ratio,
                    classified_ratio,
                    focused_seconds,
                    distracted_seconds,
                    away_seconds,
                    unknown_seconds,
                    evidence_status,
                    detector_version,
                    raw_result_json,
                    created_at
                FROM focus_reports
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, int_value(limit, 10)),),
            ).fetchall()
        return rows_to_dicts(rows)
