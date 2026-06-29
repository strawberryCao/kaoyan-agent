from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    get_connection,
    json_dumps,
    json_loads,
    local_day_bounds_utc,
    rows_to_dicts,
    utc_now,
)


class RawEventRepository:
    def create(
        self,
        content: str,
        role: str = "",
        session_id: Optional[int] = None,
        project_id: Optional[int] = None,
        subject: str = "",
        source_type: str = "manual",
        source_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        created_at = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO raw_events (
                    project_id,
                    session_id,
                    subject,
                    role,
                    content,
                    source_type,
                    source_id,
                    metadata_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    session_id,
                    subject.strip(),
                    role,
                    content,
                    source_type,
                    source_id,
                    json_dumps(metadata or {}, {}),
                    created_at,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        return self.list_by_project_and_date(project_id=None, date_str=date_str)

    def list_by_project_and_date(
        self,
        project_id: Optional[int],
        date_str: str,
    ) -> List[Dict[str, Any]]:
        start_at, end_at = local_day_bounds_utc(date_str)
        project_clause = ""
        params: list[Any] = [start_at, end_at]
        if project_id is not None:
            project_clause = "AND project_id = ?"
            params.append(project_id)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    session_id,
                    subject,
                    role,
                    content,
                    source_type,
                    source_id,
                    metadata_json,
                    created_at
                FROM raw_events
                WHERE created_at >= ? AND created_at < ?
                {project_clause}
                ORDER BY created_at ASC, id ASC
                """,
                tuple(params),
            ).fetchall()

        events = rows_to_dicts(rows)
        for event in events:
            event["metadata"] = json_loads(event.get("metadata_json", "{}"), {})
        return events
