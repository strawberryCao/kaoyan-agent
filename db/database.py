import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Dict, List

from config import SCHEMA_PATH, get_settings


DEFAULT_SESSION_TITLE = "新对话"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_path():
    db_path = get_settings().database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection():
    connection = sqlite3.connect(get_db_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with closing(get_connection()) as connection:
        connection.executescript(schema)
        migrate_conversations_to_sessions(connection)
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_session_id_created_at
            ON conversations (session_id, created_at)
            """
        )
        connection.commit()


def table_has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def migrate_conversations_to_sessions(connection: sqlite3.Connection) -> None:
    if not table_has_column(connection, "conversations", "session_id"):
        connection.execute("ALTER TABLE conversations ADD COLUMN session_id INTEGER")

    orphan_count = connection.execute(
        "SELECT COUNT(*) FROM conversations WHERE session_id IS NULL"
    ).fetchone()[0]

    if orphan_count == 0:
        return

    timestamps = connection.execute(
        """
        SELECT MIN(created_at) AS created_at, MAX(created_at) AS updated_at
        FROM conversations
        WHERE session_id IS NULL
        """
    ).fetchone()
    now = utc_now()
    created_at = timestamps["created_at"] or now
    updated_at = timestamps["updated_at"] or now

    cursor = connection.execute(
        """
        INSERT INTO chat_sessions (title, summary, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        """,
        ("历史对话", "", created_at, updated_at),
    )
    legacy_session_id = int(cursor.lastrowid)
    connection.execute(
        "UPDATE conversations SET session_id = ? WHERE session_id IS NULL",
        (legacy_session_id,),
    )


def create_chat_session(title: str = DEFAULT_SESSION_TITLE) -> int:
    now = utc_now()
    title = title.strip() or DEFAULT_SESSION_TITLE
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO chat_sessions (title, summary, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (title, "", now, now),
        )
        connection.commit()
        return int(cursor.lastrowid)


def get_chat_session(session_id: int) -> Dict[str, str] | None:
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT id, title, summary, created_at, updated_at
            FROM chat_sessions
            WHERE id = ?
            """,
            (session_id,),
        ).fetchone()

    return dict(row) if row else None


def get_chat_sessions(limit: int = 30) -> List[Dict[str, str]]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, title, summary, created_at, updated_at
            FROM chat_sessions
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in rows]


def touch_chat_session(session_id: int) -> None:
    with closing(get_connection()) as connection:
        connection.execute(
            """
            UPDATE chat_sessions
            SET updated_at = ?
            WHERE id = ?
            """,
            (utc_now(), session_id),
        )
        connection.commit()


def update_chat_session_title(session_id: int, title: str) -> None:
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


def save_message(session_id: int, role: str, content: str) -> int:
    if role not in {"user", "assistant"}:
        raise ValueError("role must be either 'user' or 'assistant'")

    created_at = utc_now()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO conversations (session_id, role, content, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_id, role, content, created_at),
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


def get_messages_by_session(session_id: int, limit: int = 50) -> List[Dict[str, str]]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, session_id, role, content, created_at
            FROM conversations
            WHERE session_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        ).fetchall()

    return [dict(row) for row in reversed(rows)]
