import sqlite3
from datetime import datetime, timezone
from typing import Dict, List

from config import SCHEMA_PATH, get_settings


def get_db_path():
    db_path = get_settings().database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def get_connection():
    connection = sqlite3.connect(get_db_path())
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as connection:
        connection.executescript(schema)


def save_message(role: str, content: str) -> int:
    if role not in {"user", "assistant"}:
        raise ValueError("role must be either 'user' or 'assistant'")

    created_at = datetime.now(timezone.utc).isoformat()
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO conversations (role, content, created_at)
            VALUES (?, ?, ?)
            """,
            (role, content, created_at),
        )
        connection.commit()
        return int(cursor.lastrowid)


def list_messages(limit: int = 50) -> List[Dict[str, str]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, role, content, created_at
            FROM conversations
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(row) for row in reversed(rows)]
