from contextlib import closing
from typing import Any, Dict, Optional

from kaoyan_agent.db.database import get_connection, json_dumps, utc_now


class AgentRunRepository:
    def create(
        self,
        agent_name: str,
        workflow_name: str = "",
        request: Optional[Dict[str, Any]] = None,
        response: Optional[Dict[str, Any]] = None,
        raw_response: str = "",
        parse_status: str = "ok",
        error_message: str = "",
        project_id: Optional[int] = None,
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO agent_runs (
                    project_id,
                    agent_name,
                    workflow_name,
                    request_json,
                    response_json,
                    raw_response,
                    parse_status,
                    error_message,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    agent_name,
                    workflow_name,
                    json_dumps(request or {}, {}),
                    json_dumps(response or {}, {}),
                    raw_response,
                    parse_status,
                    error_message,
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
