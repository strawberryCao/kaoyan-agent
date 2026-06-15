from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    get_connection,
    int_value,
    local_day_bounds_utc,
    normalize_status,
    rows_to_dicts,
    utc_now,
)


STUDY_TASK_STATUSES = {"todo", "doing", "done", "skipped", "delayed"}


class StudyTaskRepository:
    def create(
        self,
        title: str,
        subject: str = "",
        estimated_minutes: int = 0,
        source: str = "",
        status: str = "todo",
        related_problem_id: Optional[int] = None,
        scheduled_date: Optional[str] = None,
        review_priority: int = 2,
        project_id: Optional[int] = None,
    ) -> int:
        title = title.strip()
        if not title:
            raise ValueError("title must not be empty")

        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO study_tasks (
                    project_id,
                    title,
                    subject,
                    estimated_minutes,
                    source,
                    status,
                    related_problem_id,
                    scheduled_date,
                    review_priority,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    title,
                    subject.strip(),
                    max(0, int_value(estimated_minutes, 0)),
                    source.strip(),
                    normalize_status(status, STUDY_TASK_STATUSES, "todo"),
                    related_problem_id,
                    scheduled_date,
                    review_priority,
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list(
        self,
        date_str: Optional[str] = None,
        limit: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        params: list[Any] = []
        clauses: list[str] = []
        if date_str:
            start_at, end_at = local_day_bounds_utc(date_str)
            clauses.append("created_at >= ? AND created_at < ?")
            params.extend([start_at, end_at])
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            params.append(max(1, int_value(limit, 50)))

        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    title,
                    subject,
                    estimated_minutes,
                    source,
                    related_problem_id,
                    scheduled_date,
                    status,
                    review_priority,
                    finished_at,
                    created_at,
                    updated_at
                FROM study_tasks
                {where_clause}
                ORDER BY
                    CASE status
                        WHEN 'doing' THEN 1
                        WHEN 'todo' THEN 2
                        ELSE 3
                    END,
                    review_priority DESC,
                    updated_at DESC,
                    id DESC
                {limit_clause}
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def update_status(self, task_id: int, status: str) -> bool:
        status = normalize_status(status, STUDY_TASK_STATUSES, "")
        if not status:
            raise ValueError("invalid study task status")

        with closing(get_connection()) as connection:
            finished_at = utc_now() if status == "done" else None
            cursor = connection.execute(
                """
                UPDATE study_tasks
                SET status = ?, finished_at = COALESCE(?, finished_at), updated_at = ?
                WHERE id = ?
                """,
                (status, finished_at, utc_now(), task_id),
            )
            connection.commit()
            return cursor.rowcount > 0
