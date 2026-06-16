from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    float_value,
    get_connection,
    json_dumps,
    json_loads,
    rows_to_dicts,
    utc_now,
)


class SkillMemoryRepository:
    def list(self, limit: int = 100, include_archived: bool = False) -> List[Dict[str, Any]]:
        status_clause = "" if include_archived else "WHERE status = 'active'"
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    review_id,
                    skill_name,
                    description,
                    trigger_json,
                    procedure_json,
                    merge_key,
                    confidence,
                    effectiveness_score,
                    status,
                    evidence_refs_json,
                    embedding_json,
                    last_used_at,
                    created_at,
                    updated_at
                FROM skill_memories
                {status_clause}
                ORDER BY effectiveness_score DESC, updated_at DESC, id DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        skills = rows_to_dicts(rows)
        for skill in skills:
            skill["trigger"] = json_loads(skill.get("trigger_json", "{}"), {})
            skill["procedure"] = json_loads(skill.get("procedure_json", "{}"), {})
            skill["evidence_refs"] = json_loads(skill.get("evidence_refs_json", "[]"), [])
            skill["embedding"] = json_loads(skill.get("embedding_json", "[]"), [])
        return skills

    def find_by_key(
        self,
        merge_key: str = "",
        skill_name: str = "",
    ) -> Optional[Dict[str, Any]]:
        merge_key = (merge_key or "").strip()
        skill_name = (skill_name or "").strip()
        if not merge_key and not skill_name:
            return None

        clauses = []
        params: list[Any] = []
        if merge_key:
            clauses.append("merge_key = ?")
            params.append(merge_key)
        if skill_name:
            clauses.append("skill_name = ?")
            params.append(skill_name)

        with closing(get_connection()) as connection:
            row = connection.execute(
                f"""
                SELECT
                    id,
                    review_id,
                    skill_name,
                    description,
                    trigger_json,
                    procedure_json,
                    merge_key,
                    confidence,
                    effectiveness_score,
                    status,
                    evidence_refs_json,
                    embedding_json,
                    last_used_at,
                    created_at,
                    updated_at
                FROM skill_memories
                WHERE ({' OR '.join(clauses)})
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        if not row:
            return None
        skill = dict(row)
        skill["trigger"] = json_loads(skill.get("trigger_json", "{}"), {})
        skill["procedure"] = json_loads(skill.get("procedure_json", "{}"), {})
        skill["evidence_refs"] = json_loads(skill.get("evidence_refs_json", "[]"), [])
        skill["embedding"] = json_loads(skill.get("embedding_json", "[]"), [])
        return skill

    def create(
        self,
        skill: Dict[str, Any],
        review_id: Optional[int] = None,
    ) -> Optional[int]:
        operation = str(skill.get("operation") or "insert").strip() or "insert"
        skill_name = str(skill.get("skill_name") or "").strip()
        if operation == "skip" or not skill_name:
            return None

        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO skill_memories (
                    review_id,
                    skill_name,
                    description,
                    trigger_json,
                    procedure_json,
                    merge_key,
                    confidence,
                    effectiveness_score,
                    status,
                    evidence_refs_json,
                    embedding_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    skill_name,
                    str(skill.get("description") or ""),
                    json_dumps(skill.get("trigger"), {}),
                    json_dumps(skill.get("procedure"), {}),
                    str(skill.get("merge_key") or skill_name),
                    float_value(skill.get("confidence"), 0.0),
                    float_value(skill.get("effectiveness_score"), 0.0),
                    str(skill.get("status") or "active"),
                    json_dumps(skill.get("evidence_refs"), []),
                    json_dumps(skill.get("embedding") or skill.get("embedding_json"), []),
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def update(
        self,
        skill_id: int,
        skill: Dict[str, Any],
        review_id: Optional[int] = None,
    ) -> bool:
        now = utc_now()
        with closing(get_connection()) as connection:
            current = connection.execute(
                """
                SELECT evidence_refs_json, effectiveness_score
                FROM skill_memories
                WHERE id = ?
                """,
                (skill_id,),
            ).fetchone()
            if not current:
                return False

            existing_refs = json_loads(current["evidence_refs_json"], [])
            incoming_refs = skill.get("evidence_refs") or []
            evidence_refs = existing_refs + [
                ref for ref in incoming_refs if ref not in existing_refs
            ]
            effectiveness = max(
                float_value(current["effectiveness_score"], 0.0),
                float_value(skill.get("effectiveness_score"), 0.0),
            )
            cursor = connection.execute(
                """
                UPDATE skill_memories
                SET
                    review_id = COALESCE(?, review_id),
                    skill_name = COALESCE(NULLIF(?, ''), skill_name),
                    description = COALESCE(NULLIF(?, ''), description),
                    trigger_json = COALESCE(NULLIF(?, '{}'), trigger_json),
                    procedure_json = COALESCE(NULLIF(?, '{}'), procedure_json),
                    merge_key = COALESCE(NULLIF(?, ''), merge_key),
                    confidence = ?,
                    effectiveness_score = ?,
                    status = COALESCE(NULLIF(?, ''), status),
                    evidence_refs_json = ?,
                    embedding_json = COALESCE(NULLIF(?, '[]'), embedding_json),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    review_id,
                    str(skill.get("skill_name") or ""),
                    str(skill.get("description") or ""),
                    json_dumps(skill.get("trigger"), {}),
                    json_dumps(skill.get("procedure"), {}),
                    str(skill.get("merge_key") or ""),
                    float_value(skill.get("confidence"), 0.0),
                    effectiveness,
                    str(skill.get("status") or ""),
                    json_dumps(evidence_refs, []),
                    json_dumps(skill.get("embedding") or skill.get("embedding_json"), []),
                    now,
                    skill_id,
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

    def record_operation(
        self,
        operation: str,
        candidate: Dict[str, Any],
        review_id: Optional[int] = None,
        skill_id: Optional[int] = None,
        reason: str = "",
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO skill_operations (
                    review_id,
                    skill_id,
                    operation,
                    candidate_json,
                    reason,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    skill_id,
                    operation,
                    json_dumps(candidate, {}),
                    reason,
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
