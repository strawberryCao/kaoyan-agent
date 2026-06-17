import json
import sqlite3
from contextlib import closing
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List

from kaoyan_agent.core.paths import SCHEMA_PATH
from kaoyan_agent.core.settings import get_settings

DEFAULT_PROJECT_NAME = "默认备考项目"


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
    """Initialize schema and apply forward-compatible migrations."""

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with closing(get_connection()) as connection:
        connection.executescript(schema)
        migrate_conversations_to_sessions(connection)
        migrate_v02_tables(connection)
        migrate_v03_tables(connection)
        migrate_v04_tables(connection)
        migrate_v05_project_space(connection)
        migrate_v06_memory_system(connection)
        migrate_v07_nightly_diagnostics(connection)
        migrate_v08_feature_cde_compatibility(connection)
        migrate_v09_online_actions_and_timer_state(connection)
        migrate_v10_pending_actions_and_trace(connection)
        migrate_v11_fix_trace_columns(connection)
        migrate_v12_memory_backends(connection)
        migrate_v13_nightly_memory_chain(connection)
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
    """Move legacy conversations without session_id into one historical session."""

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
    """Backfill nightly review, problem, and memory fields from early schemas."""

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


def migrate_v03_tables(connection: sqlite3.Connection) -> None:
    """Backfill evidence refs, memory state, task links, and raw_events."""

    ensure_column(connection, "problem_board", "evidence_refs_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(connection, "problem_board", "merge_key", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "problem_board", "merged_into_problem_id", "INTEGER")

    ensure_column(connection, "memories", "status", "TEXT NOT NULL DEFAULT 'active'")
    ensure_column(connection, "memories", "valid_from", "TEXT")
    ensure_column(connection, "memories", "last_used_at", "TEXT")
    ensure_column(connection, "memories", "effectiveness_score", "REAL NOT NULL DEFAULT 0.0")
    ensure_column(connection, "memories", "evidence_refs_json", "TEXT NOT NULL DEFAULT '[]'")

    ensure_column(connection, "study_tasks", "related_problem_id", "INTEGER")
    ensure_column(connection, "study_tasks", "scheduled_date", "TEXT")
    ensure_column(connection, "study_tasks", "finished_at", "TEXT")

    connection.execute(
        """
        INSERT INTO raw_events (
            session_id,
            role,
            content,
            source_type,
            source_id,
            metadata_json,
            created_at
        )
        SELECT
            c.session_id,
            c.role,
            c.content,
            'chat_message',
            c.id,
            '{"backfilled_from":"conversations"}',
            c.created_at
        FROM conversations c
        WHERE NOT EXISTS (
            SELECT 1
            FROM raw_events e
            WHERE e.source_type = 'chat_message'
            AND e.source_id = c.id
        )
        """
    )

    connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_events_created_at ON raw_events (created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_events_session_created_at ON raw_events (session_id, created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_events_source ON raw_events (source_type, source_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_agent_created_at ON agent_runs (agent_name, created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_tool_runs_tool_created_at ON tool_runs (tool_name, created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_evidence_links_target ON evidence_links (target_type, target_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_evidence_links_evidence ON evidence_links (evidence_type, evidence_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_status ON memories (status)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_daily_memory_graphs_date ON daily_memory_graphs (graph_date)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_global_memory_nodes_type ON global_memory_nodes (node_type, status)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_study_tasks_scheduled_date ON study_tasks (scheduled_date)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_practice_reviews_problem ON practice_reviews (related_problem_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_motivation_items_created_at ON motivation_items (created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_score_records_subject_date ON score_records (subject, exam_date)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_focus_sessions_task ON focus_sessions (task_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_focus_state_events_session ON focus_state_events (focus_session_id, created_at)")


def migrate_v04_tables(connection: sqlite3.Connection) -> None:
    """Add parse failure diagnostics for structured nightly memory output."""

    ensure_column(connection, "nightly_reviews", "error_message", "TEXT NOT NULL DEFAULT ''")


def ensure_default_project_id(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        SELECT id
        FROM projects
        WHERE status = 'active'
        ORDER BY id ASC
        LIMIT 1
        """
    ).fetchone()
    if row:
        return int(row["id"])

    now = utc_now()
    cursor = connection.execute(
        """
        INSERT INTO projects (
            name,
            description,
            exam_year,
            target_school,
            target_major,
            subjects_json,
            status,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            DEFAULT_PROJECT_NAME,
            "历史数据默认归属项目。",
            "",
            "",
            "",
            '["数学一","英语一","408","政治"]',
            "active",
            now,
            now,
        ),
    )
    return int(cursor.lastrowid)


def migrate_v05_project_space(connection: sqlite3.Connection) -> None:
    """Add project-space ownership and backfill legacy rows to a default project."""

    default_project_id = ensure_default_project_id(connection)

    for table in [
        "chat_sessions",
        "conversations",
        "raw_events",
        "agent_runs",
        "nightly_reviews",
        "problem_board",
        "memories",
        "study_tasks",
        "practice_reviews",
        "mistake_cards",
        "motivation_items",
        "score_records",
        "score_analysis_reports",
        "focus_sessions",
    ]:
        ensure_column(connection, table, "project_id", "INTEGER")

    ensure_column(connection, "raw_events", "subject", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "memories", "subject", "TEXT NOT NULL DEFAULT ''")

    for table in [
        "chat_sessions",
        "agent_runs",
        "nightly_reviews",
        "problem_board",
        "memories",
        "study_tasks",
        "practice_reviews",
        "mistake_cards",
        "motivation_items",
        "score_records",
        "score_analysis_reports",
        "focus_sessions",
    ]:
        connection.execute(
            f"UPDATE {table} SET project_id = ? WHERE project_id IS NULL",
            (default_project_id,),
        )

    connection.execute(
        """
        UPDATE conversations
        SET project_id = COALESCE(
            (
                SELECT chat_sessions.project_id
                FROM chat_sessions
                WHERE chat_sessions.id = conversations.session_id
            ),
            ?
        )
        WHERE project_id IS NULL
        """,
        (default_project_id,),
    )
    connection.execute(
        """
        UPDATE raw_events
        SET project_id = COALESCE(
            (
                SELECT chat_sessions.project_id
                FROM chat_sessions
                WHERE chat_sessions.id = raw_events.session_id
            ),
            ?
        )
        WHERE project_id IS NULL
        """,
        (default_project_id,),
    )

    connection.execute("CREATE INDEX IF NOT EXISTS idx_projects_status_updated_at ON projects (status, updated_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_project_updated_at ON chat_sessions (project_id, updated_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_conversations_project_created_at ON conversations (project_id, created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_raw_events_project_created_at ON raw_events (project_id, created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_nightly_reviews_project_date ON nightly_reviews (project_id, review_date)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_problem_board_project_status ON problem_board (project_id, status)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_project_type ON memories (project_id, memory_type)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_study_tasks_project_status ON study_tasks (project_id, status)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_score_records_project_subject_date ON score_records (project_id, subject, exam_date)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_score_analysis_reports_project_date ON score_analysis_reports (project_id, report_date)")


def migrate_v06_memory_system(connection: sqlite3.Connection) -> None:
    """Add graph, embedding, and skill-operation compatibility columns."""

    ensure_column(connection, "problem_board", "embedding_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(connection, "nightly_reviews", "skill_updates_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(connection, "nightly_reviews", "gate_results_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(connection, "memories", "embedding_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(connection, "global_memory_nodes", "embedding_json", "TEXT NOT NULL DEFAULT '[]'")

    ensure_column(connection, "skill_memories", "review_id", "INTEGER")
    ensure_column(connection, "skill_memories", "merge_key", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "skill_memories", "confidence", "REAL NOT NULL DEFAULT 0.0")
    ensure_column(connection, "skill_memories", "embedding_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(connection, "skill_memories", "last_used_at", "TEXT")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS skill_operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER,
            skill_id INTEGER,
            operation TEXT NOT NULL,
            candidate_json TEXT NOT NULL DEFAULT '{}',
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (review_id) REFERENCES nightly_reviews(id) ON DELETE SET NULL,
            FOREIGN KEY (skill_id) REFERENCES skill_memories(id) ON DELETE SET NULL
        )
        """
    )

    connection.execute("CREATE INDEX IF NOT EXISTS idx_skill_memories_status ON skill_memories (status, updated_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_skill_operations_review_id ON skill_operations (review_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_problem_board_merge_key ON problem_board (merge_key)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_memories_merge_key ON memories (merge_key)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_skill_memories_merge_key ON skill_memories (merge_key)")


def migrate_v07_nightly_diagnostics(connection: sqlite3.Connection) -> None:
    """Add candidate-level validation diagnostics for Nightly Memory."""

    ensure_column(connection, "nightly_reviews", "validation_errors_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(
        connection,
        "nightly_reviews",
        "normalization_diagnostics_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )
    ensure_column(connection, "nightly_reviews", "candidate_results_json", "TEXT NOT NULL DEFAULT '[]'")


def migrate_v08_feature_cde_compatibility(connection: sqlite3.Connection) -> None:
    """Additive fields used by integrated C/D feature workflows."""

    ensure_column(connection, "study_tasks", "reason", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "focus_sessions", "task_title", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "focus_sessions", "subject", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "focus_sessions", "actual_seconds", "INTEGER NOT NULL DEFAULT 0")
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_focus_sessions_started_at
        ON focus_sessions (started_at)
        """
    )


def migrate_v09_online_actions_and_timer_state(connection: sqlite3.Connection) -> None:
    """Add online action idempotency and DB-backed timer state fields."""

    ensure_column(connection, "focus_sessions", "timer_status", "TEXT NOT NULL DEFAULT 'ended'")
    ensure_column(connection, "focus_sessions", "segment_started_at", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "focus_sessions", "accumulated_seconds", "INTEGER NOT NULL DEFAULT 0")
    connection.execute(
        """
        UPDATE focus_sessions
        SET timer_status = CASE
            WHEN ended_at IS NULL AND completion_status = 'running' THEN 'running'
            WHEN ended_at IS NULL AND completion_status = 'paused' THEN 'paused'
            WHEN ended_at IS NULL AND completion_status = 'unknown' THEN 'running'
            ELSE 'ended'
        END
        WHERE timer_status IS NULL OR timer_status = '' OR timer_status IN ('finished', 'ended')
        """
    )
    connection.execute(
        """
        UPDATE focus_sessions
        SET segment_started_at = COALESCE(segment_started_at, started_at)
        WHERE timer_status = 'running'
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS online_action_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            session_id INTEGER,
            user_event_id INTEGER,
            action_key TEXT NOT NULL UNIQUE,
            route TEXT NOT NULL DEFAULT '',
            action_type TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            result_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL,
            FOREIGN KEY (user_event_id) REFERENCES raw_events(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_online_action_runs_key
        ON online_action_runs (action_key)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_online_action_runs_session
        ON online_action_runs (session_id, created_at)
        """
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_focus_sessions_timer_status
        ON focus_sessions (timer_status, updated_at)
        """
    )


def migrate_v10_pending_actions_and_trace(connection: sqlite3.Connection) -> None:
    """Add persistent pending actions and per-step online execution traces."""

    ensure_column(connection, "agent_runs", "session_id", "INTEGER")
    ensure_column(connection, "agent_runs", "user_message_id", "INTEGER")
    ensure_column(connection, "agent_runs", "user_event_id", "INTEGER")
    ensure_column(connection, "agent_runs", "assistant_message_id", "INTEGER")
    ensure_column(connection, "agent_runs", "duration_ms", "INTEGER NOT NULL DEFAULT 0")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            session_id INTEGER,
            user_event_id INTEGER,
            assistant_message_id INTEGER,
            pending_key TEXT NOT NULL UNIQUE,
            action_type TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending_confirmation'
                CHECK (status IN ('pending_confirmation', 'confirmed', 'dismissed', 'completed')),
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '{}',
            created_target_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL,
            FOREIGN KEY (user_event_id) REFERENCES raw_events(id) ON DELETE SET NULL,
            FOREIGN KEY (assistant_message_id) REFERENCES conversations(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_trace_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_run_id INTEGER NOT NULL,
            session_id INTEGER,
            user_message_id INTEGER,
            user_event_id INTEGER,
            assistant_message_id INTEGER,
            step_order INTEGER NOT NULL DEFAULT 0,
            step_name TEXT NOT NULL DEFAULT '',
            step_type TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'ok',
            input_summary TEXT NOT NULL DEFAULT '',
            output_summary TEXT NOT NULL DEFAULT '',
            decision_summary TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL DEFAULT '',
            duration_ms INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL,
            FOREIGN KEY (user_message_id) REFERENCES conversations(id) ON DELETE SET NULL,
            FOREIGN KEY (user_event_id) REFERENCES raw_events(id) ON DELETE SET NULL,
            FOREIGN KEY (assistant_message_id) REFERENCES conversations(id) ON DELETE SET NULL
        )
        """
    )

def migrate_v11_fix_trace_columns(connection: sqlite3.Connection) -> None:
    """Backfill trace/pending columns before any dependent indexes are created."""

    ensure_column(connection, "agent_runs", "session_id", "INTEGER")
    ensure_column(connection, "agent_runs", "user_message_id", "INTEGER")
    ensure_column(connection, "agent_runs", "user_event_id", "INTEGER")
    ensure_column(connection, "agent_runs", "assistant_message_id", "INTEGER")
    ensure_column(connection, "agent_runs", "duration_ms", "INTEGER NOT NULL DEFAULT 0")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pending_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            session_id INTEGER,
            user_event_id INTEGER,
            assistant_message_id INTEGER,
            pending_key TEXT NOT NULL UNIQUE,
            action_type TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending_confirmation'
                CHECK (status IN ('pending_confirmation', 'confirmed', 'dismissed', 'completed')),
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '{}',
            created_target_id INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL,
            FOREIGN KEY (user_event_id) REFERENCES raw_events(id) ON DELETE SET NULL,
            FOREIGN KEY (assistant_message_id) REFERENCES conversations(id) ON DELETE SET NULL
        )
        """
    )
    ensure_column(connection, "pending_actions", "project_id", "INTEGER")
    ensure_column(connection, "pending_actions", "session_id", "INTEGER")
    ensure_column(connection, "pending_actions", "user_event_id", "INTEGER")
    ensure_column(connection, "pending_actions", "assistant_message_id", "INTEGER")
    ensure_column(connection, "pending_actions", "pending_key", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "pending_actions", "action_type", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "pending_actions", "status", "TEXT NOT NULL DEFAULT 'pending_confirmation'")
    ensure_column(connection, "pending_actions", "payload_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(connection, "pending_actions", "result_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(connection, "pending_actions", "created_target_id", "INTEGER")
    ensure_column(connection, "pending_actions", "created_at", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "pending_actions", "updated_at", "TEXT NOT NULL DEFAULT ''")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_trace_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_run_id INTEGER NOT NULL,
            session_id INTEGER,
            user_message_id INTEGER,
            user_event_id INTEGER,
            assistant_message_id INTEGER,
            step_order INTEGER NOT NULL DEFAULT 0,
            step_name TEXT NOT NULL DEFAULT '',
            step_type TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'ok',
            input_summary TEXT NOT NULL DEFAULT '',
            output_summary TEXT NOT NULL DEFAULT '',
            decision_summary TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            error_message TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            ended_at TEXT NOT NULL DEFAULT '',
            duration_ms INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE SET NULL,
            FOREIGN KEY (user_message_id) REFERENCES conversations(id) ON DELETE SET NULL,
            FOREIGN KEY (user_event_id) REFERENCES raw_events(id) ON DELETE SET NULL,
            FOREIGN KEY (assistant_message_id) REFERENCES conversations(id) ON DELETE SET NULL
        )
        """
    )
    ensure_column(connection, "agent_trace_steps", "agent_run_id", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection, "agent_trace_steps", "session_id", "INTEGER")
    ensure_column(connection, "agent_trace_steps", "user_message_id", "INTEGER")
    ensure_column(connection, "agent_trace_steps", "user_event_id", "INTEGER")
    ensure_column(connection, "agent_trace_steps", "assistant_message_id", "INTEGER")
    ensure_column(connection, "agent_trace_steps", "step_order", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection, "agent_trace_steps", "step_name", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "agent_trace_steps", "step_type", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "agent_trace_steps", "status", "TEXT NOT NULL DEFAULT 'ok'")
    ensure_column(connection, "agent_trace_steps", "input_summary", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "agent_trace_steps", "output_summary", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "agent_trace_steps", "decision_summary", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "agent_trace_steps", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(connection, "agent_trace_steps", "error_message", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "agent_trace_steps", "started_at", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "agent_trace_steps", "ended_at", "TEXT NOT NULL DEFAULT ''")
    ensure_column(connection, "agent_trace_steps", "duration_ms", "INTEGER NOT NULL DEFAULT 0")

    connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_assistant_message ON agent_runs (assistant_message_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_runs_session_created_at ON agent_runs (session_id, created_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_agent_trace_steps_run ON agent_trace_steps (agent_run_id, step_order)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_key ON pending_actions (pending_key)")
    duplicate_pending_key = connection.execute(
        """
        SELECT pending_key
        FROM pending_actions
        WHERE pending_key IS NOT NULL AND pending_key != ''
        GROUP BY pending_key
        HAVING COUNT(*) > 1
        LIMIT 1
        """
    ).fetchone()
    if duplicate_pending_key is None:
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_pending_actions_key_unique
            ON pending_actions (pending_key)
            WHERE pending_key IS NOT NULL AND pending_key != ''
            """
        )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_message ON pending_actions (assistant_message_id, status)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_pending_actions_session ON pending_actions (session_id, created_at)")


def migrate_v12_memory_backends(connection: sqlite3.Connection) -> None:
    """Add sqlite graph backend tables used beside SQLite and Chroma."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_key TEXT NOT NULL UNIQUE,
            node_type TEXT NOT NULL DEFAULT '',
            ref_type TEXT NOT NULL DEFAULT '',
            ref_id INTEGER,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            embedding_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edge_key TEXT NOT NULL UNIQUE,
            source_node_key TEXT NOT NULL,
            target_node_key TEXT NOT NULL,
            relation_type TEXT NOT NULL DEFAULT '',
            weight REAL NOT NULL DEFAULT 1.0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_graph_nodes_type_ref ON graph_nodes (node_type, ref_type, ref_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_graph_nodes_status_updated ON graph_nodes (status, updated_at)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges (source_node_key, relation_type)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges (target_node_key, relation_type)")


def migrate_v13_nightly_memory_chain(connection: sqlite3.Connection) -> None:
    """Add the formal Nightly Memory graph chain without rewriting old data."""

    ensure_column(connection, "nightly_reviews", "index_sync_status_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(connection, "nightly_reviews", "inserted_counts_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(connection, "memories", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(connection, "daily_memory_graphs", "node_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection, "daily_memory_graphs", "edge_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(connection, "daily_memory_graphs", "metadata_json", "TEXT NOT NULL DEFAULT '{}'")

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_graph_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            daily_graph_id INTEGER NOT NULL,
            node_key TEXT NOT NULL,
            node_type TEXT NOT NULL DEFAULT '',
            ref_type TEXT NOT NULL DEFAULT '',
            ref_id INTEGER,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (daily_graph_id) REFERENCES daily_memory_graphs(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            daily_graph_id INTEGER NOT NULL,
            source_node_key TEXT NOT NULL,
            target_node_key TEXT NOT NULL,
            relation_type TEXT NOT NULL DEFAULT '',
            weight REAL NOT NULL DEFAULT 1.0,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (daily_graph_id) REFERENCES daily_memory_graphs(id) ON DELETE CASCADE
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS global_graph_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_key TEXT NOT NULL UNIQUE,
            node_type TEXT NOT NULL DEFAULT '',
            ref_type TEXT NOT NULL DEFAULT '',
            ref_id INTEGER,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            confidence REAL NOT NULL DEFAULT 0.0,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS global_graph_edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            edge_key TEXT NOT NULL UNIQUE,
            source_node_key TEXT NOT NULL,
            target_node_key TEXT NOT NULL,
            relation_type TEXT NOT NULL DEFAULT '',
            weight REAL NOT NULL DEFAULT 1.0,
            updated_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )

    connection.execute(
        """
        UPDATE daily_memory_graphs
        SET
            node_count = CASE
                WHEN node_count = 0 THEN json_array_length(COALESCE(nodes_json, '[]'))
                ELSE node_count
            END,
            edge_count = CASE
                WHEN edge_count = 0 THEN json_array_length(COALESCE(edges_json, '[]'))
                ELSE edge_count
            END
        WHERE nodes_json IS NOT NULL OR edges_json IS NOT NULL
        """
    )

    connection.execute("CREATE INDEX IF NOT EXISTS idx_daily_graph_nodes_graph ON daily_graph_nodes (daily_graph_id, node_type)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_daily_graph_nodes_key ON daily_graph_nodes (node_key)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_daily_graph_edges_graph ON daily_graph_edges (daily_graph_id, relation_type)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_daily_graph_edges_source ON daily_graph_edges (source_node_key)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_daily_graph_edges_target ON daily_graph_edges (target_node_key)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_global_graph_nodes_key ON global_graph_nodes (node_key)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_global_graph_nodes_type_status ON global_graph_nodes (node_type, status)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_global_graph_edges_source ON global_graph_edges (source_node_key, relation_type)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_global_graph_edges_target ON global_graph_edges (target_node_key, relation_type)")


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


def clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    number = int_value(value, default)
    return max(minimum, min(maximum, number))


def normalize_status(value: str, allowed: set[str], default: str) -> str:
    status = (value or "").strip()
    return status if status in allowed else default
