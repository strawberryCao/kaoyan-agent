from contextlib import closing
from typing import Any, Dict, List, Optional

from kaoyan_agent.db.database import (
    ensure_default_project_id,
    get_connection,
    rows_to_dicts,
    utc_now,
)


DEFAULT_SESSION_TITLE = "新对话"


class ChatRepository:
    default_session_title = DEFAULT_SESSION_TITLE

    def create_session(
        self,
        title: str = DEFAULT_SESSION_TITLE,
        project_id: Optional[int] = None,
    ) -> int:
        now = utc_now()
        title = title.strip() or DEFAULT_SESSION_TITLE
        with closing(get_connection()) as connection:
            if project_id is None:
                project_id = ensure_default_project_id(connection)
            cursor = connection.execute(
                """
                INSERT INTO chat_sessions (project_id, title, summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, title, "", now, now),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT id, project_id, title, summary, created_at, updated_at
                FROM chat_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_sessions(
        self,
        limit: int = 30,
        project_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        where_clause = ""
        params: list[Any] = []
        if project_id is not None:
            where_clause = "WHERE project_id = ?"
            params.append(project_id)
        params.append(limit)
        with closing(get_connection()) as connection:
            rows = connection.execute(
                f"""
                SELECT id, project_id, title, summary, created_at, updated_at
                FROM chat_sessions
                {where_clause}
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
        return rows_to_dicts(rows)

    def update_session_title(self, session_id: int, title: str) -> None:
        title = title.strip() or DEFAULT_SESSION_TITLE
        with closing(get_connection()) as connection:
            connection.execute(
                """
                UPDATE chat_sessions
                SET title = ?, updated_at = ?
                WHERE id = ?
                """,
                (title, utc_now(), session_id),
            )
            connection.commit()

    def save_message(
        self,
        session_id: int,
        role: str,
        content: str,
        project_id: Optional[int] = None,
    ) -> int:
        if role not in {"user", "assistant"}:
            raise ValueError("role must be either 'user' or 'assistant'")

        created_at = utc_now()
        with closing(get_connection()) as connection:
            if project_id is None:
                row = connection.execute(
                    "SELECT project_id FROM chat_sessions WHERE id = ?",
                    (session_id,),
                ).fetchone()
                project_id = int(row["project_id"]) if row and row["project_id"] is not None else None
            if project_id is None:
                project_id = ensure_default_project_id(connection)
            cursor = connection.execute(
                """
                INSERT INTO conversations (project_id, session_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project_id, session_id, role, content, created_at),
            )
            connection.execute(
                """
                UPDATE chat_sessions
                SET updated_at = ?
                WHERE id = ?
                """,
                (created_at, session_id),
            )
            connection.commit()
            return int(cursor.lastrowid)

    def list_messages(self, session_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, session_id, role, content, created_at
                FROM conversations
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return rows_to_dicts(list(reversed(rows)))
