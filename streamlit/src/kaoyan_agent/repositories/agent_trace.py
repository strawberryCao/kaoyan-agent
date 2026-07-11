from __future__ import annotations

from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import get_connection, json_dumps, json_loads, rows_to_dicts, utc_now


class AgentTraceRepository:
    def start_run(
        self,
        *,
        session_id: int,
        user_message_id: int,
        user_event_id: int,
        user_input: str,
        project_id: Optional[int] = None,
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO agent_runs (
                    project_id,
                    session_id,
                    user_message_id,
                    user_event_id,
                    agent_name,
                    workflow_name,
                    request_json,
                    response_json,
                    raw_response,
                    parse_status,
                    error_message,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'ChatAgent', 'online_session', ?, '{}', '', 'running', '', ?)
                """,
                (
                    project_id,
                    session_id,
                    user_message_id,
                    user_event_id,
                    json_dumps({"user_input": user_input}, {}),
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def add_step(
        self,
        agent_run_id: int,
        *,
        step_name: str,
        step_type: str,
        status: str,
        input_summary: str = "",
        output_summary: str = "",
        decision_summary: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        error_message: str = "",
        session_id: Optional[int] = None,
        user_message_id: Optional[int] = None,
        user_event_id: Optional[int] = None,
        assistant_message_id: Optional[int] = None,
        duration_ms: int = 0,
    ) -> int:
        now = utc_now()
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(step_order), 0) + 1 AS next_order
                FROM agent_trace_steps
                WHERE agent_run_id = ?
                """,
                (agent_run_id,),
            ).fetchone()
            step_order = int(row["next_order"] or 1)
            cursor = connection.execute(
                """
                INSERT INTO agent_trace_steps (
                    agent_run_id,
                    session_id,
                    user_message_id,
                    user_event_id,
                    assistant_message_id,
                    step_order,
                    step_name,
                    step_type,
                    status,
                    input_summary,
                    output_summary,
                    decision_summary,
                    metadata_json,
                    error_message,
                    started_at,
                    ended_at,
                    duration_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    agent_run_id,
                    session_id,
                    user_message_id,
                    user_event_id,
                    assistant_message_id,
                    step_order,
                    step_name,
                    step_type,
                    status,
                    input_summary[:500],
                    output_summary[:500],
                    decision_summary[:500],
                    json_dumps(metadata or {}, {}),
                    error_message[:500],
                    now,
                    now,
                    max(0, int(duration_ms or 0)),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def finish_run(
        self,
        agent_run_id: int,
        *,
        assistant_message_id: Optional[int],
        status: str,
        response: Optional[Dict[str, Any]] = None,
        raw_response: str = "",
        error_message: str = "",
        duration_ms: int = 0,
    ) -> bool:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE agent_runs
                SET
                    assistant_message_id = ?,
                    parse_status = ?,
                    response_json = ?,
                    raw_response = ?,
                    error_message = ?,
                    duration_ms = ?
                WHERE id = ?
                """,
                (
                    assistant_message_id,
                    status,
                    json_dumps(response or {}, {}),
                    raw_response,
                    error_message,
                    max(0, int(duration_ms or 0)),
                    agent_run_id,
                ),
            )
            connection.execute(
                """
                UPDATE agent_trace_steps
                SET assistant_message_id = COALESCE(assistant_message_id, ?)
                WHERE agent_run_id = ?
                """,
                (assistant_message_id, agent_run_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def get_run_by_message(self, assistant_message_id: int) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM agent_runs
                WHERE assistant_message_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (assistant_message_id,),
            ).fetchone()
        return self._normalize_run(row) if row else None

    def list_steps(self, agent_run_id: int) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM agent_trace_steps
                WHERE agent_run_id = ?
                ORDER BY step_order ASC, id ASC
                """,
                (agent_run_id,),
            ).fetchall()
        steps = rows_to_dicts(rows)
        for step in steps:
            step["metadata"] = json_loads(step.get("metadata_json", "{}"), {})
        return steps

    def list_recent_runs(
        self,
        limit: int = 50,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        filters = filters or {}
        where = ["workflow_name = 'online_session'"]
        params: list[Any] = []
        if filters.get("status"):
            where.append("parse_status = ?")
            params.append(str(filters["status"]))
        if filters.get("session_id"):
            where.append("session_id = ?")
            params.append(int(filters["session_id"]))
        params.append(max(1, int(limit or 50)))
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM agent_runs
                WHERE {' AND '.join(where)}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return [self._normalize_run(row) for row in rows]

    @staticmethod
    def _normalize_run(row) -> Dict[str, Any]:
        data = dict(row)
        data["request"] = json_loads(data.get("request_json", "{}"), {})
        data["response"] = json_loads(data.get("response_json", "{}"), {})
        return data
