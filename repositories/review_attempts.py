"""复刷记录 Repository"""

from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import get_connection, rows_to_dicts, utc_now


class ReviewAttemptRepository:
    """复刷记录持久化"""
    
    def create(
        self,
        subject: str,
        topic: str,
        question: str,
        hint_content: str,
        user_answer: str,
        ai_feedback: str,
        is_correct: int,
        confidence: int,
        source_type: str = "manual",
        source_id: Optional[int] = None,
        project_id: Optional[int] = None,
    ) -> int:
        """保存一次复刷记录"""
        
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO review_attempts (
                    project_id, source_type, source_id,
                    subject, topic, question, hint_content,
                    user_answer, ai_feedback, is_correct, confidence, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id, source_type, source_id,
                    subject, topic, question, hint_content,
                    user_answer, ai_feedback, is_correct, confidence, utc_now()
                )
            )
            connection.commit()
            return int(cursor.lastrowid)
    
    def list_by_subject(
        self,
        subject: str,
        limit: int = 50,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """获取某科目的复刷记录"""
        
        where_parts = ["subject = ?"]
        params: List[Any] = [subject]
        
        if project_id is not None:
            where_parts.append("project_id = ?")
            params.append(project_id)
        
        params.append(limit)
        
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT id, subject, topic, question, hint_content,
                       user_answer, ai_feedback, is_correct, confidence, created_at
                FROM review_attempts
                WHERE {' AND '.join(where_parts)}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params
            ).fetchall()
        
        return rows_to_dicts(rows)
    
    def get_statistics(
        self,
        subject: str,
        project_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """获取复刷统计"""
        
        where_parts = ["subject = ?"]
        params: List[Any] = [subject]
        
        if project_id is not None:
            where_parts.append("project_id = ?")
            params.append(project_id)
        
        with closing(get_connection()) as connection:
            row = connection.execute(
                f"""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct_count,
                    SUM(CASE WHEN is_correct = 0 THEN 1 ELSE 0 END) as wrong_count,
                    SUM(CASE WHEN is_correct = -1 THEN 1 ELSE 0 END) as partial_count,
                    AVG(confidence) as avg_confidence
                FROM review_attempts
                WHERE {' AND '.join(where_parts)}
                """,
                params
            ).fetchone()
        
        if row and row['total']:
            return {
                "total": row['total'],
                "correct_count": row['correct_count'] or 0,
                "wrong_count": row['wrong_count'] or 0,
                "partial_count": row['partial_count'] or 0,
                "avg_confidence": round(row['avg_confidence'] or 0, 1),
                "correct_rate": round((row['correct_count'] or 0) / row['total'] * 100, 1)
            }
        
        return {
            "total": 0,
            "correct_count": 0,
            "wrong_count": 0,
            "partial_count": 0,
            "avg_confidence": 0,
            "correct_rate": 0
        }
