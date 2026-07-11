from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    get_connection,
    int_value,
    rows_to_dicts,
    utc_now,
)


class MotivationRepository:
    def create_item(
        self,
        sign_type: str,
        sign_level: str,
        content: str,
        suggested_action: str,
        estimated_minutes: int = 0,
        can_add_to_task_board: bool = True,
        created_task_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO motivation_items (
                    project_id,
                    sign_type,
                    sign_level,
                    content,
                    suggested_action,
                    estimated_minutes,
                    can_add_to_task_board,
                    created_task_id,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    sign_type,
                    sign_level,
                    content,
                    suggested_action,
                    max(0, int_value(estimated_minutes, 0)),
                    1 if can_add_to_task_board else 0,
                    created_task_id,
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_items(
        self,
        limit: int = 20,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        where_clause = ""
        params: list[Any] = []
        if project_id is not None:
            where_clause = "WHERE project_id = ?"
            params.append(project_id)
        params.append(max(1, int_value(limit, 20)))
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    sign_type,
                    sign_level,
                    content,
                    suggested_action,
                    estimated_minutes,
                    can_add_to_task_board,
                    created_task_id,
                    created_at
                FROM motivation_items
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

