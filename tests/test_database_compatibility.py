import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.db import database
from kaoyan_agent.repositories.conversation_repository import ChatRepository
from kaoyan_agent.repositories.memory_repository import MemoryRepository
from kaoyan_agent.repositories.problem_repository import ProblemRepository
from kaoyan_agent.repositories.project_repository import ProjectRepository


class DatabaseCompatibilityTest(unittest.TestCase):
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
