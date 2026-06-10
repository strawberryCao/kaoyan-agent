from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from db.database import get_connection, utc_now
from schemas.focus_session import (
    FocusSessionCreate,
    FocusSessionFinish,
    FocusSessionRecord,
    FocusStats,
)
from schemas.task import DailyTaskStatus


class FocusSessionRepository:
    def create_session(self, payload: FocusSessionCreate, started_at: str) -> int:
        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO focus_sessions (
                    task_id, task_title, subject, planned_minutes,
                    actual_seconds, pause_count, started_at, ended_at,
                    completed, reflection, created_at
                )
                VALUES (?, ?, ?, ?, 0, 0, ?, NULL, 0, '', ?)
                """,
                (
                    payload.task_id,
                    payload.task_title,
                    payload.subject,
                    payload.planned_minutes,
                    started_at,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def finish_session(
        self,
        session_id: int,
        payload: FocusSessionFinish,
        ended_at: str,
    ) -> FocusSessionRecord:
        with closing(get_connection()) as connection:
            connection.execute(
                """
                UPDATE focus_sessions
                SET actual_seconds = ?,
                    pause_count = ?,
                    ended_at = ?,
                    completed = ?,
                    reflection = ?
                WHERE id = ?
                """,
                (
                    payload.actual_seconds,
                    payload.pause_count,
                    ended_at,
                    int(payload.completed),
                    payload.reflection.strip(),
                    session_id,
                ),
            )
            connection.commit()

        record = self.get_session_by_id(session_id)
        if record is None:
            raise RuntimeError(f"Failed to load focus session {session_id}")
        return record

    def get_session_by_id(self, session_id: int) -> Optional[FocusSessionRecord]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id, task_id, task_title, subject, planned_minutes,
                    actual_seconds, pause_count, started_at, ended_at,
                    completed, reflection, created_at
                FROM focus_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def list_recent_sessions(self, limit: int = 20) -> List[FocusSessionRecord]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id, task_id, task_title, subject, planned_minutes,
                    actual_seconds, pause_count, started_at, ended_at,
                    completed, reflection, created_at
                FROM focus_sessions
                WHERE ended_at IS NOT NULL
                ORDER BY ended_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_sessions_by_date(self, plan_date: str) -> List[FocusSessionRecord]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id, task_id, task_title, subject, planned_minutes,
                    actual_seconds, pause_count, started_at, ended_at,
                    completed, reflection, created_at
                FROM focus_sessions
                WHERE ended_at IS NOT NULL
                  AND date(started_at) = ?
                ORDER BY started_at DESC, id DESC
                """,
                (plan_date,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_stats(self) -> FocusStats:
        today = date.today().isoformat()
        week_start = (date.today() - timedelta(days=6)).isoformat()

        with closing(get_connection()) as connection:
            today_rows = connection.execute(
                """
                SELECT actual_seconds, completed
                FROM focus_sessions
                WHERE ended_at IS NOT NULL
                  AND date(started_at) = ?
                """,
                (today,),
            ).fetchall()

            week_rows = connection.execute(
                """
                SELECT actual_seconds, completed
                FROM focus_sessions
                WHERE ended_at IS NOT NULL
                  AND date(started_at) >= ?
                """,
                (week_start,),
            ).fetchall()

            total_rows = connection.execute(
                """
                SELECT actual_seconds, completed
                FROM focus_sessions
                WHERE ended_at IS NOT NULL
                """
            ).fetchall()

            daily_rows = connection.execute(
                """
                SELECT date(started_at) AS day, SUM(actual_seconds) AS total_seconds
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
            minutes = round(sum(int(row["actual_seconds"]) for row in rows) / 60, 1)
            completed = sum(1 for row in rows if int(row["completed"]) == 1)
            return sessions, minutes, completed

        today_sessions, today_minutes, today_completed = summarize(today_rows)
        week_sessions, week_minutes, week_completed = summarize(week_rows)
        total_sessions, total_minutes, total_completed = summarize(total_rows)

        completion_rate = 0.0
        if total_sessions:
            completion_rate = round(total_completed / total_sessions * 100, 1)

        daily_minutes = {
            row["day"]: round(int(row["total_seconds"]) / 60, 1)
            for row in daily_rows
        }

        return FocusStats(
            today_sessions=today_sessions,
            today_focus_minutes=today_minutes,
            today_completed=today_completed,
            week_sessions=week_sessions,
            week_focus_minutes=week_minutes,
            week_completed=week_completed,
            total_sessions=total_sessions,
            total_focus_minutes=total_minutes,
            completion_rate=completion_rate,
            daily_minutes=daily_minutes,
        )

    def list_all_for_review(self, limit: int = 100) -> List[FocusSessionRecord]:
        """供成员2夜间复盘读取专注记录。"""
        return self.list_recent_sessions(limit=limit)

    @staticmethod
    def _row_to_record(row) -> FocusSessionRecord:
        return FocusSessionRecord(
            id=int(row["id"]),
            task_id=int(row["task_id"]) if row["task_id"] is not None else None,
            task_title=row["task_title"],
            subject=row["subject"],
            planned_minutes=int(row["planned_minutes"]),
            actual_seconds=int(row["actual_seconds"]),
            pause_count=int(row["pause_count"]),
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            completed=bool(int(row["completed"])),
            reflection=row["reflection"],
            created_at=row["created_at"],
        )
