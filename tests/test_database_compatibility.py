import tempfile
import unittest
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.db import database
from kaoyan_agent.repositories.conversation_repository import ChatRepository
from kaoyan_agent.repositories.memory_repository import MemoryRepository
from kaoyan_agent.repositories.problem_repository import ProblemRepository
from kaoyan_agent.repositories.project_repository import ProjectRepository


class DatabaseCompatibilityTest(unittest.TestCase):
    def test_init_db_upgrades_legacy_trace_tables_missing_new_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    CREATE TABLE agent_runs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER,
                        agent_name TEXT NOT NULL DEFAULT '',
                        workflow_name TEXT NOT NULL DEFAULT '',
                        request_json TEXT NOT NULL DEFAULT '{}',
                        response_json TEXT NOT NULL DEFAULT '{}',
                        raw_response TEXT NOT NULL DEFAULT '',
                        parse_status TEXT NOT NULL DEFAULT 'ok',
                        error_message TEXT NOT NULL DEFAULT '',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE pending_actions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pending_key TEXT NOT NULL DEFAULT '',
                        action_type TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'pending_confirmation',
                        payload_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE agent_trace_steps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        agent_run_id INTEGER NOT NULL,
                        step_name TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'ok',
                        started_at TEXT NOT NULL
                    )
                    """
                )
                connection.commit()

            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                with closing(sqlite3.connect(db_path)) as connection:
                    agent_run_columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(agent_runs)").fetchall()
                    }
                    trace_columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(agent_trace_steps)").fetchall()
                    }
                    pending_columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(pending_actions)").fetchall()
                    }
                    trace_indexes = {
                        row[1]
                        for row in connection.execute("PRAGMA index_list(agent_trace_steps)").fetchall()
                    }
                    pending_indexes = {
                        row[1]
                        for row in connection.execute("PRAGMA index_list(pending_actions)").fetchall()
                    }
                    run_indexes = {
                        row[1]
                        for row in connection.execute("PRAGMA index_list(agent_runs)").fetchall()
                    }

            self.assertIn("assistant_message_id", agent_run_columns)
            self.assertIn("session_id", agent_run_columns)
            self.assertIn("assistant_message_id", trace_columns)
            self.assertIn("step_order", trace_columns)
            self.assertIn("assistant_message_id", pending_columns)
            self.assertIn("updated_at", pending_columns)
            self.assertIn("idx_agent_trace_steps_run", trace_indexes)
            self.assertIn("idx_pending_actions_message", pending_indexes)
            self.assertIn("idx_pending_actions_session", pending_indexes)
            self.assertIn("idx_agent_runs_assistant_message", run_indexes)

    def test_default_compatibility_record_exists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                compat_record = ProjectRepository().ensure_default_project()

                self.assertTrue(compat_record["id"])
                self.assertIn("408", compat_record["subjects"])

    def test_new_chat_does_not_require_ui_scope(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                chat_repository = ChatRepository()

                session_id = chat_repository.create_session("global chat")
                sessions = chat_repository.list_sessions(limit=10)

                self.assertIn(session_id, [row["id"] for row in sessions])

    def test_global_problem_and_memory_reads_include_compatibility_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                compat = ProjectRepository()
                first_scope = compat.ensure_default_project()
                second_scope_id = compat.create_project("compat scope")

                problem_repository = ProblemRepository()
                memory_repository = MemoryRepository()
                first_problem_id = problem_repository.create(
                    {"description": "first", "value_score": 3},
                    project_id=first_scope["id"],
                )
                second_problem_id = problem_repository.create(
                    {"description": "second", "value_score": 5},
                    project_id=second_scope_id,
                )
                first_memory_id = memory_repository.create(
                    {"content": "first memory"},
                    project_id=first_scope["id"],
                )
                second_memory_id = memory_repository.create(
                    {"content": "second memory"},
                    project_id=second_scope_id,
                )

                problem_ids = {row["id"] for row in problem_repository.list_open()}
                memory_ids = {row["id"] for row in memory_repository.list()}

                self.assertEqual(problem_ids, {first_problem_id, second_problem_id})
                self.assertEqual(memory_ids, {first_memory_id, second_memory_id})


if __name__ == "__main__":
    unittest.main()
