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
        return problems

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
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

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
