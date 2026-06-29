from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import get_connection, json_dumps, rows_to_dicts, utc_now


class ScoreRepository:
    def create_record(
        self,
        subject: str,
        score: float,
        full_score: float,
        exam_type: str,
        exam_date: str,
        note: str = "",
        project_id: Optional[int] = None,
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO score_records (
                    project_id,
                    subject,
                    score,
                    full_score,
                    exam_type,
                    exam_date,
                    note,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    subject.strip(),
                    float(score),
                    float(full_score),
                    exam_type.strip(),
                    exam_date,
                    note.strip(),
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_records(
        self,
        subject: Optional[str] = None,
        limit: int = 50,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if subject:
            clauses.append("subject = ?")
            params.append(subject)
        if project_id is not None:
            clauses.append("project_id = ?")
            params.append(project_id)
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, limit))
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    subject,
                    score,
                    full_score,
                    exam_type,
                    exam_date,
                    note,
                    created_at
                FROM score_records
                {where_clause}
                ORDER BY exam_date DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def create_analysis_report(
        self,
        subject: str,
        report_date: str,
        latest_score: Optional[float] = None,
        score_delta: Optional[float] = None,
        risk_level: str = "",
        ai_suggestion: str = "",
        raw_result: Optional[Dict[str, Any]] = None,
        project_id: Optional[int] = None,
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO score_analysis_reports (
                    project_id,
                    subject,
                    report_date,
                    latest_score,
                    score_delta,
                    risk_level,
                    ai_suggestion,
                    raw_result_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    subject.strip(),
                    report_date,
                    latest_score,
                    score_delta,
                    risk_level,
                    ai_suggestion,
                    json_dumps(raw_result or {}, {}),
                    utc_now(),
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

