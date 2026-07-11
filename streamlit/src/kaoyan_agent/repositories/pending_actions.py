from __future__ import annotations

from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import get_connection, json_dumps, json_loads, rows_to_dicts, utc_now


PENDING_STATUSES = {"pending_confirmation", "confirmed", "dismissed", "completed"}


class PendingActionRepository:
    def create_pending(
        self,
        *,
        pending_key: str,
        action_type: str,
        payload: Dict[str, Any],
        session_id: Optional[int],
        user_event_id: Optional[int],
        assistant_message_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        now = utc_now()
        with closing(get_connection()) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO pending_actions (
                    project_id,
                    session_id,
                    user_event_id,
                    assistant_message_id,
                    pending_key,
                    action_type,
                    status,
                    payload_json,
                    result_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending_confirmation', ?, '{}', ?, ?)
                """,
                (
                    project_id,
                    session_id,
                    user_event_id,
                    assistant_message_id,
                    pending_key,
                    action_type,
                    json_dumps(payload, {}),
                    now,
                    now,
                ),
            )
            connection.commit()
        return self.get_by_key(pending_key) or {}

    def get(self, pending_action_id: int) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    project_id,
                    session_id,
                    user_event_id,
                    assistant_message_id,
                    pending_key,
                    action_type,
                    status,
                    payload_json,
                    result_json,
                    created_target_id,
                    created_at,
                    updated_at
                FROM pending_actions
                WHERE id = ?
                """,
                (pending_action_id,),
            ).fetchone()
        return self._normalize(row) if row else None

    def get_by_key(self, pending_key: str) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    project_id,
                    session_id,
                    user_event_id,
                    assistant_message_id,
                    pending_key,
                    action_type,
                    status,
                    payload_json,
                    result_json,
                    created_target_id,
                    created_at,
                    updated_at
                FROM pending_actions
                WHERE pending_key = ?
                """,
                (pending_key,),
            ).fetchone()
        return self._normalize(row) if row else None

    def list_for_message(self, assistant_message_id: int) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    project_id,
                    session_id,
                    user_event_id,
                    assistant_message_id,
                    pending_key,
                    action_type,
                    status,
                    payload_json,
                    result_json,
                    created_target_id,
                    created_at,
                    updated_at
                FROM pending_actions
                WHERE assistant_message_id = ?
                ORDER BY id ASC
                """,
                (assistant_message_id,),
            ).fetchall()
        return [self._normalize(row) for row in rows]

    def bind_to_assistant_message(self, pending_action_id: int, assistant_message_id: int) -> bool:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE pending_actions
                SET assistant_message_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (assistant_message_id, utc_now(), pending_action_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def confirm(self, pending_action_id: int, result: Optional[Dict[str, Any]] = None) -> bool:
        return self._set_status(pending_action_id, "confirmed", result=result)

    def dismiss(self, pending_action_id: int, reason: str = "") -> bool:
        return self._set_status(
            pending_action_id,
            "dismissed",
            result={"dismiss_reason": reason},
        )

    def complete(
        self,
        pending_action_id: int,
        *,
        created_target_id: Optional[int],
        result: Dict[str, Any],
    ) -> bool:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE pending_actions
                SET
                    status = 'completed',
                    result_json = ?,
                    created_target_id = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    json_dumps(result, {}),
                    created_target_id,
                    utc_now(),
                    pending_action_id,
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

    def _set_status(
        self,
        pending_action_id: int,
        status: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        if status not in PENDING_STATUSES:
            raise ValueError("invalid pending action status")
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE pending_actions
                SET status = ?, result_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    json_dumps(result or {}, {}),
                    utc_now(),
                    pending_action_id,
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _normalize(row) -> Dict[str, Any]:
        data = dict(row)
        data["payload"] = json_loads(data.get("payload_json", "{}"), {})
        data["result"] = json_loads(data.get("result_json", "{}"), {})
        return data
