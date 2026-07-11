from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    get_connection,
    int_value,
    float_value,
    json_dumps,
    json_loads,
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
                    embedding_json,
                    metadata_json,
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
        memories = rows_to_dicts(rows)
        for memory in memories:
            memory["evidence_refs"] = json_loads(memory.get("evidence_refs_json", "[]"), [])
            memory["embedding"] = json_loads(memory.get("embedding_json", "[]"), [])
            memory["metadata"] = json_loads(memory.get("metadata_json", "{}"), {})
        return memories

    def find_by_merge_key(
        self,
        merge_key: str,
        project_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        merge_key = (merge_key or "").strip()
        if not merge_key:
            return None

        where = "merge_key = ?"
        params: list[Any] = [merge_key]
        if project_id is not None:
            where += " AND project_id = ?"
            params.append(project_id)

        with closing(get_connection()) as connection:
            row = connection.execute(
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
                    embedding_json,
                    metadata_json,
                    subject,
                    created_at,
                    updated_at
                FROM memories
                WHERE {where}
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        if not row:
            return None
        memory = dict(row)
        memory["evidence_refs"] = json_loads(memory.get("evidence_refs_json", "[]"), [])
        memory["embedding"] = json_loads(memory.get("embedding_json", "[]"), [])
        memory["metadata"] = json_loads(memory.get("metadata_json", "{}"), {})
        return memory

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
                    embedding_json,
                    metadata_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json_dumps(memory.get("embedding") or memory.get("embedding_json"), []),
                    json_dumps(memory.get("metadata") or memory.get("metadata_json"), {}),
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def update(
        self,
        memory_id: int,
        memory: Dict[str, Any],
        review_id: Optional[int] = None,
    ) -> bool:
        content = str(memory.get("content") or "").strip()
        now = utc_now()
        with closing(get_connection()) as connection:
            current = connection.execute(
                """
                SELECT evidence_refs_json, effectiveness_score
                FROM memories
                WHERE id = ?
                """,
                (memory_id,),
            ).fetchone()
            if not current:
                return False

            existing_refs = json_loads(current["evidence_refs_json"], [])
            incoming_refs = memory.get("evidence_refs") or []
            evidence_refs = existing_refs + [
                ref for ref in incoming_refs if ref not in existing_refs
            ]
            effectiveness = max(
                float_value(current["effectiveness_score"], 0.0),
                float_value(memory.get("effectiveness_score"), 0.0),
            )
            cursor = connection.execute(
                """
                UPDATE memories
                SET
                    operation = ?,
                    memory_type = COALESCE(NULLIF(?, ''), memory_type),
                    content = COALESCE(NULLIF(?, ''), content),
                    importance = ?,
                    confidence = ?,
                    merge_key = COALESCE(NULLIF(?, ''), merge_key),
                    reason = ?,
                    review_id = COALESCE(?, review_id),
                    status = COALESCE(NULLIF(?, ''), status),
                    valid_from = COALESCE(NULLIF(?, ''), valid_from),
                    evidence_refs_json = ?,
                    subject = COALESCE(NULLIF(?, ''), subject),
                    embedding_json = COALESCE(NULLIF(?, '[]'), embedding_json),
                    metadata_json = COALESCE(NULLIF(?, '{}'), metadata_json),
                    effectiveness_score = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    str(memory.get("operation") or "update"),
                    str(memory.get("memory_type") or ""),
                    content,
                    int_value(memory.get("importance"), 3),
                    float_value(memory.get("confidence"), 0.0),
                    str(memory.get("merge_key") or ""),
                    str(memory.get("reason") or ""),
                    review_id,
                    str(memory.get("status") or ""),
                    str(memory.get("valid_from") or ""),
                    json_dumps(evidence_refs, []),
                    str(memory.get("subject") or ""),
                    json_dumps(memory.get("embedding") or memory.get("embedding_json"), []),
                    json_dumps(memory.get("metadata") or memory.get("metadata_json"), {}),
                    effectiveness,
                    now,
                    memory_id,
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

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
