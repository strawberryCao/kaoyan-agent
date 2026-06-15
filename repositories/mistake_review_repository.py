from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import get_connection, rows_to_dicts, utc_now, clamp_int


class MistakeReviewRepository:
    """错题卡 Repository - 支持掌握度分数"""
    
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
        mastery_score: int = 0,
        project_id: Optional[int] = None,
    ) -> int:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO mistake_cards (
                    project_id, subject, chapter, question, analysis,
                    mistake_reason, knowledge_points, review_priority,
                    mastery_status, mastery_score, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (project_id, subject, chapter, question, analysis,
                 mistake_reason, knowledge_points, review_priority,
                 mastery_status, clamp_int(mastery_score, 0, 0, 100),
                 utc_now(), utc_now())
            )
            connection.commit()
            return int(cursor.lastrowid)
    
    def update_mastery(
        self,
        card_id: int,
        mastery_status: str,
        mastery_score: Optional[int] = None,
    ) -> bool:
        """更新掌握状态和掌握度分数"""
        
        if mastery_score is not None:
            mastery_score = clamp_int(mastery_score, 0, 0, 100)
            with closing(get_connection()) as connection:
                cursor = connection.execute(
                    """
                    UPDATE mistake_cards
                    SET mastery_status = ?, mastery_score = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (mastery_status, mastery_score, utc_now(), card_id)
                )
                connection.commit()
                return cursor.rowcount > 0
        else:
            with closing(get_connection()) as connection:
                cursor = connection.execute(
                    """
                    UPDATE mistake_cards
                    SET mastery_status = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (mastery_status, utc_now(), card_id)
                )
                connection.commit()
                return cursor.rowcount > 0
    
    def get_card_by_question(self, question: str, project_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """根据问题内容查找错题卡"""
        
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT id, subject, chapter, question, analysis, mistake_reason,
                       knowledge_points, review_priority, mastery_status, mastery_score
                FROM mistake_cards
                WHERE question = ? AND (project_id = ? OR project_id IS NULL)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (question, project_id)
            ).fetchone()
        
        return dict(row) if row else None
    
    def list_cards(
        self,
        limit: int = 100,
        project_id: Optional[int] = None,
        sort_by: str = "review_priority",
    ) -> List[Dict[str, Any]]:
        """列出错题卡，支持排序"""
        
        sort_map = {
            "review_priority": "review_priority DESC, mastery_score ASC",
            "mastery_score": "mastery_score ASC, review_priority DESC",
            "created_at": "created_at DESC",
            "subject": "subject ASC, review_priority DESC",
        }
        order_by = sort_map.get(sort_by, "review_priority DESC, mastery_score ASC")
        
        where_clause = ""
        params: List[Any] = []
        if project_id is not None:
            where_clause = "WHERE project_id = ?"
            params.append(project_id)
        params.append(limit)
        
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT id, subject, chapter, question, analysis, mistake_reason,
                       knowledge_points, review_priority, mastery_status, mastery_score,
                       created_at, updated_at
                FROM mistake_cards
                {where_clause}
                ORDER BY {order_by}
                LIMIT ?
                """,
                params
            ).fetchall()
        
        return rows_to_dicts(rows)
