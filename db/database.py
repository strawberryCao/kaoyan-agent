import json
import sqlite3
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

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
        migrate_v02_tables(connection)
        connection.commit()


def table_has_column(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    column_definition: str,
) -> None:
    if not table_has_column(connection, table, column):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_definition}")


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


def migrate_v02_tables(connection: sqlite3.Connection) -> None:
    ensure_column(connection, "nightly_reviews", "raw_result_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(connection, "nightly_reviews", "raw_response", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "nightly_reviews", "parse_status", "TEXT NOT NULL DEFAULT 'ok'")

    ensure_column(connection, "problem_board", "review_id", "INTEGER")
    ensure_column(connection, "problem_board", "evidence_json", "TEXT NOT NULL DEFAULT '[]'")
    if table_has_column(connection, "problem_board", "evidence"):
        connection.execute(
            """
            UPDATE problem_board
            SET evidence_json = evidence
            WHERE (evidence_json IS NULL OR evidence_json = '' OR evidence_json = '[]')
            AND evidence IS NOT NULL
            AND evidence != ''
            """
        )
    if table_has_column(connection, "problem_board", "source_review_id"):
        connection.execute(
            """
            UPDATE problem_board
            SET review_id = source_review_id
            WHERE review_id IS NULL
            AND source_review_id IS NOT NULL
            """
        )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_problem_board_review_id
        ON problem_board (review_id)
        """
    )

    ensure_column(connection, "memories", "operation", "TEXT NOT NULL DEFAULT 'insert'")
    ensure_column(connection, "memories", "reason", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "memories", "review_id", "INTEGER")
    if table_has_column(connection, "memories", "source_review_id"):
        connection.execute(
            """
            UPDATE memories
            SET review_id = source_review_id
            WHERE review_id IS NULL
            AND source_review_id IS NOT NULL
            """
        )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memories_review_id
        ON memories (review_id)
        """
    )


def rows_to_dicts(rows: List[sqlite3.Row]) -> List[Dict[str, Any]]:
    return [dict(row) for row in rows]


def local_day_bounds_utc(date_str: str) -> tuple[str, str]:
    target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    local_tz = datetime.now().astimezone().tzinfo
    start_local = datetime.combine(target_date, time.min, tzinfo=local_tz)
    end_local = datetime.combine(
        target_date + timedelta(days=1), time.min, tzinfo=local_tz
    )
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


def json_dumps(value: Any, fallback: Any) -> str:
    try:
        return json.dumps(value if value is not None else fallback, ensure_ascii=False)
    except TypeError:
        return json.dumps(fallback, ensure_ascii=False)


def json_loads(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value) if value else fallback
    except json.JSONDecodeError:
        return fallback


def int_value(value: Any, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def get_chat_session(session_id: int) -> Optional[Dict[str, Any]]:
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


def get_chat_sessions(limit: int = 30) -> List[Dict[str, Any]]:
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

    return rows_to_dicts(rows)


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


def get_messages_by_session(session_id: int, limit: int = 50) -> List[Dict[str, Any]]:
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

    return rows_to_dicts(list(reversed(rows)))


def get_conversations_by_date(date_str: str) -> List[Dict[str, Any]]:
    start_at, end_at = local_day_bounds_utc(date_str)
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT
                c.id,
                c.session_id,
                s.title AS session_title,
                c.role,
                c.content,
                c.created_at
            FROM conversations c
            JOIN chat_sessions s ON s.id = c.session_id
            WHERE c.created_at >= ? AND c.created_at < ?
            ORDER BY c.created_at ASC, c.id ASC
            """,
            (start_at, end_at),
        ).fetchall()

    return rows_to_dicts(rows)


def get_sessions_by_date(date_str: str) -> List[Dict[str, Any]]:
    start_at, end_at = local_day_bounds_utc(date_str)
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, title, summary, created_at, updated_at
            FROM chat_sessions s
            WHERE
                (s.created_at >= ? AND s.created_at < ?)
                OR (s.updated_at >= ? AND s.updated_at < ?)
                OR EXISTS (
                    SELECT 1
                    FROM conversations c
                    WHERE c.session_id = s.id
                    AND c.created_at >= ?
                    AND c.created_at < ?
                )
            ORDER BY updated_at DESC, id DESC
            """,
            (start_at, end_at, start_at, end_at, start_at, end_at),
        ).fetchall()

    return rows_to_dicts(rows)


def get_all_memories() -> List[Dict[str, Any]]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                review_id,
                operation,
                memory_type,
                content,
                importance,
                confidence,
                merge_key,
                reason,
                created_at,
                updated_at
            FROM memories
            ORDER BY importance DESC, updated_at DESC, id DESC
            """
        ).fetchall()

    return rows_to_dicts(rows)


def get_open_problems() -> List[Dict[str, Any]]:
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
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
                created_at,
                updated_at
            FROM problem_board
            WHERE status = 'open'
            ORDER BY value_score DESC, severity DESC, updated_at DESC, id DESC
            """
        ).fetchall()

    problems = rows_to_dicts(rows)
    for problem in problems:
        problem["evidence"] = json_loads(problem.get("evidence_json", "[]"), [])
    return problems


def save_nightly_review(
    review_date: str,
    result: Dict[str, Any],
    raw_response: str = "",
    parse_status: str = "ok",
) -> int:
    now = utc_now()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO nightly_reviews (
                review_date,
                daily_summary,
                key_events_json,
                discovered_problems_json,
                memory_updates_json,
                next_actions_json,
                raw_result_json,
                raw_response,
                parse_status,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_date,
                str(result.get("daily_summary", "")),
                json_dumps(result.get("key_events"), []),
                json_dumps(result.get("discovered_problems"), []),
                json_dumps(result.get("memory_updates"), []),
                json_dumps(result.get("next_actions"), []),
                json_dumps(result, {}),
                raw_response,
                parse_status,
                now,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def insert_problem(problem: Dict[str, Any], review_id: Optional[int] = None) -> int:
    now = utc_now()
    evidence = problem.get("evidence", [])
    if isinstance(evidence, str):
        evidence = [evidence] if evidence.strip() else []

    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO problem_board (
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
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
                now,
                now,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def insert_memory(
    memory: Dict[str, Any], review_id: Optional[int] = None
) -> Optional[int]:
    operation = str(memory.get("operation") or "insert").strip() or "insert"
    content = str(memory.get("content") or "").strip()
    if operation == "skip" or not content:
        return None

    now = utc_now()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO memories (
                operation,
                memory_type,
                content,
                importance,
                confidence,
                merge_key,
                reason,
                review_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation,
                str(memory.get("memory_type") or "strategy"),
                content,
                int_value(memory.get("importance"), 1),
                float_value(memory.get("confidence"), 0.0),
                str(memory.get("merge_key") or ""),
                str(memory.get("reason") or ""),
                review_id,
                now,
                now,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
