from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    clamp_int,
    get_connection,
    int_value,
    normalize_status,
    rows_to_dicts,
    utc_now,
)


MASTERY_STATUSES = {"unmastered", "reviewing", "mastered"}


class PracticeReviewRepository:
    """Formal mistake-card repository.

    The project still keeps the legacy ``practice_reviews`` table for practice
    attempt feedback, but generated mistake cards use ``mistake_cards`` as the
    single official mistake pool. ``MistakeReviewRepository`` is only an alias
    to this repository so chat, UI, and workflows read/write the same table.
    """

    def create_card(
        self,
        subject: str,
        chapter: str,
        question: str,
        analysis: str,
        mistake_reason: str = "unknown",
        knowledge_points: str = "",
        review_priority: int = 1,
        mastery_status: str = "unmastered",
        project_id: Optional[int] = None,
    ) -> int:
        question = question.strip()
        if not question:
            raise ValueError("question must not be empty")

        now = utc_now()
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO mistake_cards (
                    project_id,
                    subject,
                    chapter,
                    question,
                    analysis,
                    mistake_reason,
                    knowledge_points,
                    review_priority,
                    mastery_status,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    subject.strip(),
                    chapter.strip(),
                    question,
                    analysis.strip(),
                    mistake_reason.strip() or "unknown",
                    knowledge_points.strip(),
                    clamp_int(review_priority, 1, 1, 5),
                    normalize_status(mastery_status, MASTERY_STATUSES, "unmastered"),
                    now,
                    now,
                ),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_cards(
        self,
        limit: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        limit_clause = ""
        where_clause = ""
        params: list[Any] = []
        if project_id is not None:
            where_clause = "WHERE project_id = ?"
            params.append(project_id)
        if limit is not None:
            limit_clause = "LIMIT ?"
            params.append(max(1, int_value(limit, 100)))

        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT
                    id,
                    project_id,
                    subject,
                    chapter,
                    question,
                    analysis,
                    mistake_reason,
                    knowledge_points,
                    review_priority,
                    mastery_status,
                    created_at,
                    updated_at
                FROM mistake_cards
                {where_clause}
                ORDER BY review_priority DESC, updated_at DESC, id DESC
                {limit_clause}
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def update_mastery_status(self, card_id: int, mastery_status: str) -> bool:
        mastery_status = normalize_status(mastery_status, MASTERY_STATUSES, "")
        if not mastery_status:
            raise ValueError("invalid mastery status")

        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                UPDATE mistake_cards
                SET mastery_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (mastery_status, utc_now(), card_id),
            )
            connection.commit()
            return cursor.rowcount > 0

    def reason_counts(self, project_id: Optional[int] = None) -> List[Dict[str, Any]]:
        where_clause = ""
        params: tuple[Any, ...] = ()
        if project_id is not None:
            where_clause = "WHERE project_id = ?"
            params = (project_id,)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT mistake_reason, COUNT(*) AS count
                FROM mistake_cards
                {where_clause}
                GROUP BY mistake_reason
                ORDER BY count DESC, mistake_reason ASC
                """,
                params,
            ).fetchall()
        return rows_to_dicts(rows)
