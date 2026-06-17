from __future__ import annotations

from contextlib import closing
from typing import Any, Dict, Optional

from kaoyan_agent.db.database import get_connection, json_dumps, json_loads, utc_now


class OnlineActionRepository:
    def get_by_key(self, action_key: str) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    project_id,
                    session_id,
                    user_event_id,
                    action_key,
                    route,
                    action_type,
                    status,
                    result_json,
                    error_message,
                    created_at,
                    updated_at
                FROM online_action_runs
                WHERE action_key = ?
                """,
                (action_key,),
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["result"] = json_loads(data.get("result_json", "{}"), {})
        return data

    def create(
        self,
        *,
        action_key: str,
        route: str,
        action_type: str,
        status: str,
        result: Dict[str, Any],
        user_event_id: Optional[int] = None,
        session_id: Optional[int] = None,
        project_id: Optional[int] = None,
        error_message: str = "",
    ) -> int:
        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO online_action_runs (
                    project_id,
                    session_id,
                    user_event_id,
                    action_key,
                    route,
                    action_type,
                    status,
                    result_json,
                    error_message,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    session_id,
                    user_event_id,
                    action_key,
                    route,
                    action_type,
                    status,
                    json_dumps(result, {}),
                    error_message,
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
