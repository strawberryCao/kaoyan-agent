from contextlib import closing
from datetime import date
from typing import List, Optional

from db.database import get_connection, utc_now
from schemas.task import DailyTaskCreate, DailyTaskRecord, DailyTaskStatus


class TaskRepository:
    def _today_str(self) -> str:
        return date.today().isoformat()

    def ensure_today_plan(self) -> int:
        plan_date = self._today_str()
        now = utc_now()
        with closing(get_connection()) as connection:
            row = connection.execute(
                "SELECT id FROM daily_plans WHERE plan_date = ?",
                (plan_date,),
            ).fetchone()
            if row:
                return int(row["id"])

            cursor = connection.execute(
                """
                INSERT INTO daily_plans (plan_date, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (plan_date, now, now),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def create_task(self, payload: DailyTaskCreate) -> DailyTaskRecord:
        plan_id = self.ensure_today_plan()
        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO daily_tasks (
                    plan_id, subject, task, reason, estimated_minutes,
                    related_problem_id, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    payload.subject.strip(),
                    payload.task.strip(),
                    payload.reason.strip(),
                    payload.estimated_minutes,
                    payload.related_problem_id.strip(),
                    DailyTaskStatus.PENDING.value,
                    now,
                    now,
                ),
            )
            connection.commit()
            task_id = int(cursor.lastrowid)

        task = self.get_task_by_id(task_id)
        if task is None:
            raise RuntimeError(f"Failed to load task {task_id}")
        return task

    def list_today_tasks(self) -> List[DailyTaskRecord]:
        plan_date = self._today_str()
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    t.id, t.plan_id, t.subject, t.task, t.reason,
                    t.estimated_minutes, t.related_problem_id, t.status,
                    t.created_at, t.updated_at
                FROM daily_tasks t
                JOIN daily_plans p ON p.id = t.plan_id
                WHERE p.plan_date = ?
                ORDER BY
                    CASE t.status
                        WHEN 'in_progress' THEN 0
                        WHEN 'pending' THEN 1
                        ELSE 2
                    END,
                    t.id ASC
                """,
                (plan_date,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def get_task_by_id(self, task_id: int) -> Optional[DailyTaskRecord]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id, plan_id, subject, task, reason, estimated_minutes,
                    related_problem_id, status, created_at, updated_at
                FROM daily_tasks
                WHERE id = ?
                """,
                (task_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def update_task_status(self, task_id: int, status: DailyTaskStatus) -> None:
        with closing(get_connection()) as connection:
            connection.execute(
                """
                UPDATE daily_tasks
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status.value, utc_now(), task_id),
            )
            connection.commit()

    def seed_demo_tasks_if_empty(self) -> None:
        if self.list_today_tasks():
            return

        demo_tasks = [
            DailyTaskCreate(
                subject="数学",
                task="高数极限与连续复习",
                reason="昨日错题未消化",
                estimated_minutes=25,
            ),
            DailyTaskCreate(
                subject="408",
                task="操作系统进程调度刷题",
                reason="计划内任务",
                estimated_minutes=25,
            ),
            DailyTaskCreate(
                subject="英语",
                task="阅读理解精读 2 篇",
                reason="保持语感",
                estimated_minutes=30,
            ),
        ]
        for task in demo_tasks:
            self.create_task(task)

    @staticmethod
    def _row_to_record(row) -> DailyTaskRecord:
        return DailyTaskRecord(
            id=int(row["id"]),
            plan_id=int(row["plan_id"]),
            subject=row["subject"],
            task=row["task"],
            reason=row["reason"],
            estimated_minutes=int(row["estimated_minutes"]),
            related_problem_id=row["related_problem_id"],
            status=DailyTaskStatus(row["status"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
