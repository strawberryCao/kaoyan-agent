from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    float_value,
    get_connection,
    int_value,
    json_dumps,
    json_loads,
    rows_to_dicts,
    utc_now,
)


class ProblemRepository:
    def list_by_statuses(
        self,
        statuses: List[str],
        project_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        clean_statuses = [str(status).strip() for status in statuses if str(status).strip()]
        if not clean_statuses:
            return []
        placeholders = ",".join("?" for _ in clean_statuses)
        params: list[Any] = list(clean_statuses)
        project_clause = ""
        if project_id is not None:
            project_clause = "AND project_id = ?"
            params.append(project_id)
        params.append(max(1, int_value(limit, 100)))
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    review_id,
                    problem_type,
                    subject,
                    description,
                    evidence_json,
                    root_cause,
                    severity,
                    confidence,
                    value_score,
                    suggested_action,
                    status,
                    evidence_refs_json,
                    merge_key,
                    merged_into_problem_id,
                    embedding_json,
                    created_at,
                    updated_at
                FROM problem_board
                WHERE status IN ({placeholders})
                {project_clause}
                ORDER BY value_score DESC, severity DESC, updated_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        problems = rows_to_dicts(rows)
        for problem in problems:
            problem["evidence"] = json_loads(problem.get("evidence_json", "[]"), [])
            problem["evidence_refs"] = json_loads(problem.get("evidence_refs_json", "[]"), [])
            problem["embedding"] = json_loads(problem.get("embedding_json", "[]"), [])
        return problems

    def list_open(self, project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        project_clause = ""
        params: tuple[Any, ...] = ()
        if project_id is not None:
            project_clause = "AND project_id = ?"
            params = (project_id,)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    review_id,
                    problem_type,
                    subject,
                    description,
                    evidence_json,
                    root_cause,
                    severity,
                    confidence,
                    value_score,
                    suggested_action,
                    status,
                    evidence_refs_json,
                    merge_key,
                    merged_into_problem_id,
                    embedding_json,
                    created_at,
                    updated_at
                FROM problem_board
                WHERE status IN ('open', 'watching')
                {project_clause}
                ORDER BY value_score DESC, severity DESC, updated_at DESC, id DESC
                """,
                params,
            ).fetchall()

        problems = rows_to_dicts(rows)
        for problem in problems:
            problem["evidence"] = json_loads(problem.get("evidence_json", "[]"), [])
            problem["evidence_refs"] = json_loads(
                problem.get("evidence_refs_json", "[]"), []
            )
            problem["embedding"] = json_loads(problem.get("embedding_json", "[]"), [])
        return problems

    def find_by_merge_key(
        self,
        merge_key: str,
        project_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        merge_key = (merge_key or "").strip()
        if not merge_key:
            return None

        project_clause = ""
        params: list[Any] = [merge_key]
        if project_id is not None:
            project_clause = "AND project_id = ?"
            params.append(project_id)

        with closing(get_connection()) as connection:
            row = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    review_id,
                    problem_type,
                    subject,
                    description,
                    evidence_json,
                    root_cause,
                    severity,
                    confidence,
                    value_score,
                    suggested_action,
                    status,
                    evidence_refs_json,
                    merge_key,
                    merged_into_problem_id,
                    embedding_json,
                    created_at,
                    updated_at
                FROM problem_board
                WHERE merge_key = ?
                {project_clause}
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                tuple(params),
            ).fetchone()
        if not row:
            return None
        problem = dict(row)
        problem["evidence"] = json_loads(problem.get("evidence_json", "[]"), [])
        problem["evidence_refs"] = json_loads(problem.get("evidence_refs_json", "[]"), [])
        problem["embedding"] = json_loads(problem.get("embedding_json", "[]"), [])
        return problem

    def create(
        self,
        problem: Dict[str, Any],
        review_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> int:
        now = utc_now()
        evidence = problem.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence] if evidence.strip() else []

        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO problem_board (
                    project_id,
                    problem_type,
                    subject,
                    description,
                    evidence_json,
                    root_cause,
                    severity,
                    confidence,
                    value_score,
                    suggested_action,
                    status,
                    review_id,
                    evidence_refs_json,
                    merge_key,
                    embedding_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    str(problem.get("problem_type") or "other"),
                    str(problem.get("subject") or ""),
                    str(problem.get("description") or ""),
                    json_dumps(evidence, []),
                    str(problem.get("root_cause") or ""),
                    int_value(problem.get("severity"), 1),
                    float_value(problem.get("confidence"), 0.0),
                    int_value(problem.get("value_score"), 1),
                    str(problem.get("suggested_action") or ""),
                    str(problem.get("status") or "open"),
                    review_id,
                    json_dumps(problem.get("evidence_refs"), []),
                    str(problem.get("merge_key") or ""),
                    json_dumps(problem.get("embedding") or problem.get("embedding_json"), []),
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def update(
        self,
        problem_id: int,
        problem: Dict[str, Any],
        review_id: Optional[int] = None,
    ) -> bool:
        now = utc_now()
        evidence = problem.get("evidence", [])
        if isinstance(evidence, str):
            evidence = [evidence] if evidence.strip() else []

        with closing(get_connection()) as connection:
            current = connection.execute(
                """
                SELECT evidence_json, evidence_refs_json
                FROM problem_board
                WHERE id = ?
                """,
                (problem_id,),
            ).fetchone()
            if not current:
                return False

            existing_evidence = json_loads(current["evidence_json"], [])
            merged_evidence = existing_evidence + [
                item for item in evidence if item not in existing_evidence
            ]
            existing_refs = json_loads(current["evidence_refs_json"], [])
            incoming_refs = problem.get("evidence_refs") or []
            evidence_refs = existing_refs + [
                ref for ref in incoming_refs if ref not in existing_refs
            ]
            cursor = connection.execute(
                """
                UPDATE problem_board
                SET
                    problem_type = COALESCE(NULLIF(?, ''), problem_type),
                    subject = COALESCE(NULLIF(?, ''), subject),
                    description = COALESCE(NULLIF(?, ''), description),
                    evidence_json = ?,
                    root_cause = COALESCE(NULLIF(?, ''), root_cause),
                    severity = ?,
                    confidence = ?,
                    value_score = ?,
                    suggested_action = COALESCE(NULLIF(?, ''), suggested_action),
                    status = COALESCE(NULLIF(?, ''), status),
                    review_id = COALESCE(?, review_id),
                    evidence_refs_json = ?,
                    merge_key = COALESCE(NULLIF(?, ''), merge_key),
                    embedding_json = COALESCE(NULLIF(?, '[]'), embedding_json),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    str(problem.get("problem_type") or ""),
                    str(problem.get("subject") or ""),
                    str(problem.get("description") or ""),
                    json_dumps(merged_evidence, []),
                    str(problem.get("root_cause") or ""),
                    int_value(problem.get("severity"), 1),
                    float_value(problem.get("confidence"), 0.0),
                    int_value(problem.get("value_score"), 1),
                    str(problem.get("suggested_action") or ""),
                    str(problem.get("status") or ""),
                    review_id,
                    json_dumps(evidence_refs, []),
                    str(problem.get("merge_key") or ""),
                    json_dumps(problem.get("embedding") or problem.get("embedding_json"), []),
                    now,
                    problem_id,
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

    def update_status(self, problem_id: int, status: str) -> bool:
        status = status.strip()
        if not status:
            raise ValueError("status must not be empty")

        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE problem_board
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, utc_now(), problem_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def record_operation(
        self,
        operation: str,
        candidate: Dict[str, Any],
        review_id: Optional[int] = None,
        problem_id: Optional[int] = None,
        reason: str = "",
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO problem_operations (
                    review_id,
                    problem_id,
                    operation,
                    candidate_json,
                    reason,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    problem_id,
                    operation,
                    json_dumps(candidate, {}),
                    reason,
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)
