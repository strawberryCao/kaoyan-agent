from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    get_connection,
    int_value,
    json_dumps,
    json_loads,
    local_day_bounds_utc,
    rows_to_dicts,
    utc_now,
)


class NightlyReviewRepository:
    def create(
        self,
        review_date: str,
        result: Dict[str, Any],
        raw_response: str = "",
        parse_status: str = "ok",
        error_message: str = "",
        validation_errors: Optional[List[Dict[str, Any]]] = None,
        normalization_diagnostics: Optional[List[Dict[str, Any]]] = None,
        candidate_results: Optional[List[Dict[str, Any]]] = None,
        index_sync_status: Optional[Dict[str, Any]] = None,
        inserted_counts: Optional[Dict[str, Any]] = None,
        project_id: Optional[int] = None,
    ) -> int:
        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO nightly_reviews (
                    project_id,
                    review_date,
                    daily_summary,
                    key_events_json,
                    discovered_problems_json,
                    memory_updates_json,
                    skill_updates_json,
                    next_actions_json,
                    gate_results_json,
                    index_sync_status_json,
                    inserted_counts_json,
                    raw_result_json,
                    raw_response,
                    parse_status,
                    error_message,
                    validation_errors_json,
                    normalization_diagnostics_json,
                    candidate_results_json,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    review_date,
                    str(result.get("daily_summary", "")),
                    json_dumps(result.get("key_events"), []),
                    json_dumps(result.get("discovered_problems"), []),
                    json_dumps(result.get("memory_updates"), []),
                    json_dumps(result.get("skill_updates"), []),
                    json_dumps(result.get("next_actions"), []),
                    json_dumps(result.get("gate_results"), []),
                    json_dumps(index_sync_status, {}),
                    json_dumps(inserted_counts, {}),
                    json_dumps(result, {}),
                    raw_response,
                    parse_status,
                    error_message,
                    json_dumps(validation_errors, []),
                    json_dumps(normalization_diagnostics, []),
                    json_dumps(candidate_results, []),
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def update_chain_status(
        self,
        review_id: int,
        *,
        raw_result: Optional[Dict[str, Any]] = None,
        gate_results: Optional[List[Dict[str, Any]]] = None,
        index_sync_status: Optional[Dict[str, Any]] = None,
        inserted_counts: Optional[Dict[str, Any]] = None,
        validation_errors: Optional[List[Dict[str, Any]]] = None,
        normalization_diagnostics: Optional[List[Dict[str, Any]]] = None,
        candidate_results: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        updates: list[str] = []
        params: list[Any] = []

        if raw_result is not None:
            result = dict(raw_result)
            if gate_results is not None:
                result["gate_results"] = gate_results
            if index_sync_status is not None:
                result["index_sync_status"] = index_sync_status
            if inserted_counts is not None:
                result["inserted_counts"] = inserted_counts
            if validation_errors is not None:
                result["validation_errors"] = validation_errors
            if normalization_diagnostics is not None:
                result["normalization_diagnostics"] = normalization_diagnostics
            if candidate_results is not None:
                result["candidate_results"] = candidate_results

            updates.extend(
                [
                    "skill_updates_json = ?",
                    "gate_results_json = ?",
                    "raw_result_json = ?",
                ]
            )
            params.extend(
                [
                    json_dumps(result.get("skill_updates"), []),
                    json_dumps(gate_results if gate_results is not None else result.get("gate_results"), []),
                    json_dumps(result, {}),
                ]
            )
        elif gate_results is not None:
            updates.append("gate_results_json = ?")
            params.append(json_dumps(gate_results, []))

        if index_sync_status is not None:
            updates.append("index_sync_status_json = ?")
            params.append(json_dumps(index_sync_status, {}))
        if inserted_counts is not None:
            updates.append("inserted_counts_json = ?")
            params.append(json_dumps(inserted_counts, {}))
        if validation_errors is not None:
            updates.append("validation_errors_json = ?")
            params.append(json_dumps(validation_errors, []))
        if normalization_diagnostics is not None:
            updates.append("normalization_diagnostics_json = ?")
            params.append(json_dumps(normalization_diagnostics, []))
        if candidate_results is not None:
            updates.append("candidate_results_json = ?")
            params.append(json_dumps(candidate_results, []))

        if not updates:
            return False

        params.append(review_id)
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                f"""
                UPDATE nightly_reviews
                SET {", ".join(updates)}
                WHERE id = ?
                """,
                tuple(params),
            )
            connection.commit()
            return cursor.rowcount > 0

    def update_gate_results(
        self,
        review_id: int,
        gate_results: List[Dict[str, Any]],
        raw_result: Dict[str, Any],
        validation_errors: Optional[List[Dict[str, Any]]] = None,
        normalization_diagnostics: Optional[List[Dict[str, Any]]] = None,
        candidate_results: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        raw_result = dict(raw_result)
        raw_result["gate_results"] = gate_results
        if validation_errors is not None:
            raw_result["validation_errors"] = validation_errors
        if normalization_diagnostics is not None:
            raw_result["normalization_diagnostics"] = normalization_diagnostics
        if candidate_results is not None:
            raw_result["candidate_results"] = candidate_results
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE nightly_reviews
                SET
                    skill_updates_json = ?,
                    gate_results_json = ?,
                    raw_result_json = ?,
                    validation_errors_json = ?,
                    normalization_diagnostics_json = ?,
                    candidate_results_json = ?
                WHERE id = ?
                """,
                (
                    json_dumps(raw_result.get("skill_updates"), []),
                    json_dumps(gate_results, []),
                    json_dumps(raw_result, {}),
                    json_dumps(validation_errors, []),
                    json_dumps(normalization_diagnostics, []),
                    json_dumps(candidate_results, []),
                    review_id,
                ),
            )
            connection.commit()
            return cursor.rowcount > 0

    def list_latest(
        self,
        limit: int = 5,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        where_clause = ""
        params: list[Any] = []
        if project_id is not None:
            where_clause = "WHERE project_id = ?"
            params.append(project_id)
        params.append(max(1, int_value(limit, 5)))
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    review_date,
                    daily_summary,
                    key_events_json,
                    discovered_problems_json,
                    memory_updates_json,
                    skill_updates_json,
                    next_actions_json,
                    gate_results_json,
                    index_sync_status_json,
                    inserted_counts_json,
                    raw_result_json,
                    raw_response,
                    parse_status,
                    error_message,
                    validation_errors_json,
                    normalization_diagnostics_json,
                    candidate_results_json,
                    created_at
                FROM nightly_reviews
                {where_clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()

        reviews = rows_to_dicts(rows)
        for review in reviews:
            review["key_events"] = json_loads(review.get("key_events_json", "[]"), [])
            review["discovered_problems"] = json_loads(
                review.get("discovered_problems_json", "[]"), []
            )
            review["memory_updates"] = json_loads(
                review.get("memory_updates_json", "[]"), []
            )
            review["skill_updates"] = json_loads(
                review.get("skill_updates_json", "[]"), []
            )
            review["next_actions"] = json_loads(review.get("next_actions_json", "[]"), [])
            review["gate_results"] = json_loads(
                review.get("gate_results_json", "[]"), []
            )
            review["index_sync_status"] = json_loads(
                review.get("index_sync_status_json", "{}"), {}
            )
            review["inserted_counts"] = json_loads(
                review.get("inserted_counts_json", "{}"), {}
            )
            review["raw_result"] = json_loads(review.get("raw_result_json", "{}"), {})
            review["validation_errors"] = json_loads(
                review.get("validation_errors_json", "[]"), []
            )
            review["normalization_diagnostics"] = json_loads(
                review.get("normalization_diagnostics_json", "[]"), []
            )
            review["candidate_results"] = json_loads(
                review.get("candidate_results_json", "[]"), []
            )
        return reviews

    def list_sessions_by_date(
        self,
        date_str: str,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        start_at, end_at = local_day_bounds_utc(date_str)
        project_clause = ""
        params: list[Any] = [start_at, end_at, start_at, end_at, start_at, end_at]
        if project_id is not None:
            project_clause = "AND s.project_id = ?"
            params.append(project_id)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT id, project_id, title, summary, created_at, updated_at
                FROM chat_sessions s
                WHERE
                    (
                        (s.created_at >= ? AND s.created_at < ?)
                        OR (s.updated_at >= ? AND s.updated_at < ?)
                        OR EXISTS (
                            SELECT 1
                            FROM conversations c
                            WHERE c.session_id = s.id
                            AND c.created_at >= ?
                            AND c.created_at < ?
                        )
                    )
                    {project_clause}
                ORDER BY updated_at DESC, id DESC
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def list_focus_sessions_by_date(
        self,
        date_str: str,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        start_at, end_at = local_day_bounds_utc(date_str)
        project_clause = ""
        params: list[Any] = [start_at, end_at, start_at, end_at, start_at, end_at]
        if project_id is not None:
            project_clause = "AND project_id = ?"
            params.append(project_id)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM focus_sessions
                WHERE (
                    (created_at >= ? AND created_at < ?)
                    OR (started_at >= ? AND started_at < ?)
                    OR (updated_at >= ? AND updated_at < ?)
                )
                {project_clause}
                ORDER BY COALESCE(started_at, created_at) ASC, id ASC
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def list_mistake_cards_by_date(
        self,
        date_str: str,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        start_at, end_at = local_day_bounds_utc(date_str)
        project_clause = ""
        params: list[Any] = [start_at, end_at, start_at, end_at]
        if project_id is not None:
            project_clause = "AND project_id = ?"
            params.append(project_id)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM mistake_cards
                WHERE (
                    (created_at >= ? AND created_at < ?)
                    OR (updated_at >= ? AND updated_at < ?)
                )
                {project_clause}
                ORDER BY updated_at DESC, id DESC
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def list_study_tasks_by_date(
        self,
        date_str: str,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        start_at, end_at = local_day_bounds_utc(date_str)
        project_clause = ""
        params: list[Any] = [date_str, start_at, end_at, start_at, end_at]
        if project_id is not None:
            project_clause = "AND project_id = ?"
            params.append(project_id)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT *
                FROM study_tasks
                WHERE (
                    scheduled_date = ?
                    OR (created_at >= ? AND created_at < ?)
                    OR (updated_at >= ? AND updated_at < ?)
                )
                {project_clause}
                ORDER BY
                    CASE status
                        WHEN 'doing' THEN 1
                        WHEN 'todo' THEN 2
                        WHEN 'done' THEN 3
                        ELSE 4
                    END,
                    updated_at DESC,
                    id DESC
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def list_conversations_by_date(
        self,
        date_str: str,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        start_at, end_at = local_day_bounds_utc(date_str)
        project_clause = ""
        params: list[Any] = [start_at, end_at]
        if project_id is not None:
            project_clause = "AND c.project_id = ?"
            params.append(project_id)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    c.id,
                    c.project_id,
                    c.session_id,
                    s.title AS session_title,
                    c.role,
                    c.content,
                    c.created_at
                FROM conversations c
                JOIN chat_sessions s ON s.id = c.session_id
                WHERE c.created_at >= ? AND c.created_at < ?
                {project_clause}
                ORDER BY c.created_at ASC, c.id ASC
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)
