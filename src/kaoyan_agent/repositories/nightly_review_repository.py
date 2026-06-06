from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    get_connection,
    int_value,
    json_dumps,
    json_loads,
    local_day_bounds_utc,
    rows_to_dicts,
    utc_now,
)


class NightlyReviewRepository:
    def create(
        self,
        review_date: str,
        result: Dict[str, Any],
        raw_response: str = "",
        parse_status: str = "ok",
        error_message: str = "",
        project_id: Optional[int] = None,
    ) -> int:
        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO nightly_reviews (
                    project_id,
                    review_date,
                    daily_summary,
                    key_events_json,
                    discovered_problems_json,
                    memory_updates_json,
                    next_actions_json,
                    raw_result_json,
                    raw_response,
                    parse_status,
                    error_message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    review_date,
                    str(result.get("daily_summary", "")),
                    json_dumps(result.get("key_events"), []),
                    json_dumps(result.get("discovered_problems"), []),
                    json_dumps(result.get("memory_updates"), []),
                    json_dumps(result.get("next_actions"), []),
                    json_dumps(result, {}),
                    raw_response,
                    parse_status,
                    error_message,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_latest(
        self,
        limit: int = 5,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        where_clause = ""
        params: list[Any] = []
        if project_id is not None:
            where_clause = "WHERE project_id = ?"
            params.append(project_id)
        params.append(max(1, int_value(limit, 5)))
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    review_date,
                    daily_summary,
                    key_events_json,
                    discovered_problems_json,
                    memory_updates_json,
                    next_actions_json,
                    raw_result_json,
                    raw_response,
                    parse_status,
                    error_message,
                    created_at
                FROM nightly_reviews
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()

        reviews = rows_to_dicts(rows)
        for review in reviews:
            review["key_events"] = json_loads(review.get("key_events_json", "[]"), [])
            review["discovered_problems"] = json_loads(
                review.get("discovered_problems_json", "[]"), []
            )
            review["memory_updates"] = json_loads(
                review.get("memory_updates_json", "[]"), []
            )
            review["next_actions"] = json_loads(review.get("next_actions_json", "[]"), [])
            review["raw_result"] = json_loads(review.get("raw_result_json", "{}"), {})
        return reviews

    def list_sessions_by_date(
        self,
        date_str: str,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        start_at, end_at = local_day_bounds_utc(date_str)
        project_clause = ""
        params: list[Any] = [start_at, end_at, start_at, end_at, start_at, end_at]
        if project_id is not None:
            project_clause = "AND s.project_id = ?"
            params.append(project_id)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT id, project_id, title, summary, created_at, updated_at
                FROM chat_sessions s
                WHERE
                    (
                        (s.created_at >= ? AND s.created_at < ?)
                        OR (s.updated_at >= ? AND s.updated_at < ?)
                        OR EXISTS (
                            SELECT 1
                            FROM conversations c
                            WHERE c.session_id = s.id
                            AND c.created_at >= ?
                            AND c.created_at < ?
                        )
                    )
                    {project_clause}
                ORDER BY updated_at DESC, id DESC
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def list_conversations_by_date(
        self,
        date_str: str,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        start_at, end_at = local_day_bounds_utc(date_str)
        project_clause = ""
        params: list[Any] = [start_at, end_at]
        if project_id is not None:
            project_clause = "AND c.project_id = ?"
            params.append(project_id)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    c.id,
                    c.project_id,
                    c.session_id,
                    s.title AS session_title,
                    c.role,
                    c.content,
                    c.created_at
                FROM conversations c
                JOIN chat_sessions s ON s.id = c.session_id
                WHERE c.created_at >= ? AND c.created_at < ?
                {project_clause}
                ORDER BY c.created_at ASC, c.id ASC
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)
