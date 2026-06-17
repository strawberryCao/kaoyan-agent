from __future__ import annotations

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
from kaoyan_agent.schemas.study_task import DailyTaskCreate, DailyTaskRecord, DailyTaskStatus


STUDY_TASK_STATUSES = {"todo", "doing", "done", "skipped", "delayed"}
DAILY_TO_STUDY_STATUS = {
    DailyTaskStatus.PENDING.value: "todo",
    DailyTaskStatus.IN_PROGRESS.value: "doing",
    DailyTaskStatus.DONE.value: "done",
}
STUDY_TO_DAILY_STATUS = {
    "todo": DailyTaskStatus.PENDING,
    "doing": DailyTaskStatus.IN_PROGRESS,
    "done": DailyTaskStatus.DONE,
    "skipped": DailyTaskStatus.PENDING,
    "delayed": DailyTaskStatus.PENDING,
}


class StudyTaskRepository:
    def create(
        self,
        title: str,
        subject: str = "",
        estimated_minutes: int = 0,
        source: str = "",
        reason: str = "",
        status: str = "todo",
        related_problem_id: Optional[int] = None,
        scheduled_date: Optional[str] = None,
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
                    reason,
                    status,
                    related_problem_id,
                    scheduled_date,
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
                    reason.strip(),
                    normalize_status(status, STUDY_TASK_STATUSES, "todo"),
                    related_problem_id,
                    scheduled_date,
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
                    reason,
                    related_problem_id,
                    scheduled_date,
                    status,
                    finished_at,
                    created_at,
                    updated_at
                FROM study_tasks
                {where_clause}
                ORDER BY
                    CASE status
                        WHEN 'doing' THEN 1
                        WHEN 'todo' THEN 2
                        WHEN 'done' THEN 3
                        ELSE 4
                    END,
                    updated_at DESC,
                    id DESC
                {limit_clause}
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    project_id,
                    title,
                    subject,
                    estimated_minutes,
                    source,
                    reason,
                    related_problem_id,
                    scheduled_date,
                    status,
                    finished_at,
                    created_at,
                    updated_at
                FROM study_tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        return dict(row) if row else None

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

    def create_daily_task(
        self,
        payload: DailyTaskCreate,
        scheduled_date: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> DailyTaskRecord:
        task_id = self.create(
            title=payload.task,
            subject=payload.subject,
            estimated_minutes=payload.estimated_minutes,
            source="daily_task",
            reason=payload.reason,
            status=self.to_study_status(DailyTaskStatus.PENDING),
            related_problem_id=payload.related_problem_id,
            scheduled_date=scheduled_date,
            project_id=project_id,
        )
        record = self.get_daily_task(task_id)
        if record is None:
            raise RuntimeError(f"Failed to load study task {task_id}")
        return record

    def get_daily_task(self, task_id: int) -> Optional[DailyTaskRecord]:
        task = self.get(task_id)
        return self.to_daily_record(task) if task else None

    def list_daily_tasks(
        self,
        date_str: Optional[str] = None,
        limit: int = 100,
        project_id: Optional[int] = None,
    ) -> list[DailyTaskRecord]:
        return [
            self.to_daily_record(task)
            for task in self.list(
                date_str=date_str,
                limit=limit,
                project_id=project_id,
            )
        ]

    def update_daily_status(self, task_id: int, status: DailyTaskStatus | str) -> bool:
        return self.update_status(task_id, self.to_study_status(status))

    @staticmethod
    def to_study_status(status: DailyTaskStatus | str) -> str:
        value = status.value if isinstance(status, DailyTaskStatus) else str(status)
        return DAILY_TO_STUDY_STATUS.get(value, value)

    @staticmethod
    def to_daily_status(status: str) -> DailyTaskStatus:
        return STUDY_TO_DAILY_STATUS.get(str(status), DailyTaskStatus.PENDING)

    @classmethod
    def to_daily_record(cls, task: Dict[str, Any]) -> DailyTaskRecord:
        return DailyTaskRecord(
            id=int(task["id"]),
            subject=str(task.get("subject") or ""),
            task=str(task.get("title") or ""),
            reason=str(task.get("reason") or ""),
            estimated_minutes=int_value(task.get("estimated_minutes"), 25),
            related_problem_id=task.get("related_problem_id"),
            status=cls.to_daily_status(str(task.get("status") or "")),
            created_at=str(task.get("created_at") or ""),
            updated_at=str(task.get("updated_at") or ""),
        )
