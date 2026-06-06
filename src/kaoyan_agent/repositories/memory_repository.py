from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    get_connection,
    int_value,
    float_value,
    json_dumps,
    rows_to_dicts,
    utc_now,
)


class MemoryRepository:
    def list(
        self,
        limit: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        where_clause = ""
        params: list[Any] = []
        if project_id is not None:
            where_clause = "WHERE project_id = ?"
            params.append(project_id)
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            params.append(max(1, int_value(limit, 30)))

        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    review_id,
                    operation,
                    memory_type,
                    content,
                    importance,
                    confidence,
                    merge_key,
                    reason,
                    status,
                    valid_from,
                    last_used_at,
                    effectiveness_score,
                    evidence_refs_json,
                    subject,
                    created_at,
                    updated_at
                FROM memories
                {where_clause}
                ORDER BY importance DESC, updated_at DESC, id DESC
                {limit_clause}
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def create(
        self,
        memory: Dict[str, Any],
        review_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> Optional[int]:
        operation = str(memory.get("operation") or "insert").strip() or "insert"
        content = str(memory.get("content") or "").strip()
        if operation == "skip" or not content:
            return None

        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO memories (
                    project_id,
                    operation,
                    memory_type,
                    content,
                    importance,
                    confidence,
                    merge_key,
                    reason,
                    review_id,
                    status,
                    valid_from,
                    evidence_refs_json,
                    subject,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    operation,
                    str(memory.get("memory_type") or "strategy"),
                    content,
                    int_value(memory.get("importance"), 1),
                    float_value(memory.get("confidence"), 0.0),
                    str(memory.get("merge_key") or ""),
                    str(memory.get("reason") or ""),
                    review_id,
                    str(memory.get("status") or "active"),
                    str(memory.get("valid_from") or now),
                    json_dumps(memory.get("evidence_refs"), []),
                    str(memory.get("subject") or ""),
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def record_operation(
        self,
        operation: str,
        candidate: Dict[str, Any],
        review_id: Optional[int] = None,
        memory_id: Optional[int] = None,
        reason: str = "",
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO memory_operations (
                    review_id,
                    memory_id,
                    operation,
                    candidate_json,
                    reason,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    memory_id,
                    operation,
                    json_dumps(candidate, {}),
                    reason,
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
