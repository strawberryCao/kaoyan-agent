from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import get_connection, json_dumps, rows_to_dicts, utc_now


class FocusRepository:
    def create_session(
        self,
        task_id: Optional[int],
        planned_minutes: int,
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
                    planned_minutes,
                    started_at,
                    completion_status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, 'running', ?, ?)
                """,
                (project_id, task_id, planned_minutes, started_at or now, now, now),
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
    ) -> int:
        if state_type not in {"focused", "away", "distracted", "blocked", "unknown"}:
            state_type = "unknown"
        focus_score = max(0, min(100, int(focus_score or 0)))
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO focus_state_events (
                    focus_session_id,
                    state_type,
                    confidence,
                    focus_score,
                    explanation,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (focus_session_id, state_type, confidence, focus_score, explanation, utc_now()),
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
                    planned_minutes,
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
        return dict(row) if row else None

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
                    explanation,
                    created_at
                FROM focus_state_events
                WHERE focus_session_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (focus_session_id,),
            ).fetchall()
        return rows_to_dicts(rows)

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
    ) -> bool:
        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE focus_sessions
                SET
                    actual_minutes = ?,
                    pause_count = ?,
                    completion_status = ?,
                    reflection = ?,
                    ended_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    actual_minutes,
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
                    raw_result_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    raw_result_json,
                    created_at
                FROM focus_reports
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return rows_to_dicts(rows)

