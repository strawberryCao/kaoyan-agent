import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from kaoyan_agent.agents.focus_supervision_agent import FocusSupervisionAgent
from kaoyan_agent.agents.router import Router
from kaoyan_agent.core.settings import Settings
from kaoyan_agent.db import database
from kaoyan_agent.workflows.online_action_dispatcher import OnlineActionDispatcher
from kaoyan_agent.repositories.conversation_repository import ChatRepository
from kaoyan_agent.repositories.mistake_review_repository import MistakeReviewRepository
from kaoyan_agent.repositories.practice_review import PracticeReviewRepository
from kaoyan_agent.repositories.raw_events import RawEventRepository
from kaoyan_agent.schemas.focus import FocusTimerState, FocusTimerStatus
from kaoyan_agent.services.local_yolo_focus_recognizer import LocalYoloFocusRecognizer
from kaoyan_agent.services.llm_client import supports_vision_model
from kaoyan_agent.services.memory_backend_audit import MemoryBackendAudit
from kaoyan_agent.ui.components.pomodoro_supervision_panel import get_visible_timer_controls
from kaoyan_agent.workflows.chat_workflow import OnlineSessionWorkflow
from kaoyan_agent.workflows.focus import FocusWorkflow


def make_settings(temp_dir: str, model: str = "deepseek-v4-flash") -> Settings:
    return Settings("", None, model, database_path=Path(temp_dir) / "app.db")


class OnlineActionDispatcherTest(unittest.TestCase):
    def run_in_db(self, callback):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = make_settings(temp_dir)
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                return callback(settings)

    def count_rows(self, table: str) -> int:
        with closing(database.get_connection()) as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

    def test_chat_focus_request_starts_timer_and_records_action_result(self):
        def scenario(settings):
            session_id = ChatRepository().create_session("chat")
            result = OnlineSessionWorkflow(settings=settings).handle_user_message(
                session_id=session_id,
                user_input="我要开始番茄钟计时",
            )

            with closing(database.get_connection()) as connection:
                focus = connection.execute(
                    "SELECT task_title, timer_status FROM focus_sessions"
                ).fetchone()
                assistant_event = connection.execute(
                    """
                    SELECT metadata_json
                    FROM raw_events
                    WHERE role = 'assistant'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ).fetchone()

            metadata = json.loads(assistant_event["metadata_json"])
            self.assertEqual(result.router_decision.route, "focus")
            self.assertIn("已开始", result.assistant_text)
            self.assertEqual(focus["timer_status"], "running")
            self.assertEqual(focus["task_title"], "临时专注任务")
            self.assertEqual(metadata["action_result"]["action_type"], "focus_start")

        self.run_in_db(scenario)

    def test_same_user_event_id_is_idempotent_for_dispatcher(self):
        def scenario(settings):
            session_id = ChatRepository().create_session("chat")
            event_id = RawEventRepository().create(
                content="帮我创建一个15分钟数学任务",
                role="user",
                session_id=session_id,
                source_type="chat_message",
            )
            dispatcher = OnlineActionDispatcher(settings=settings)
            decision = Router().route("帮我创建一个15分钟数学任务")

            first = dispatcher.dispatch(
                decision=decision,
                user_input="帮我创建一个15分钟数学任务",
                session_id=session_id,
                user_event_id=event_id,
            )
            second = dispatcher.dispatch(
                decision=decision,
                user_input="帮我创建一个15分钟数学任务",
                session_id=session_id,
                user_event_id=event_id,
            )

            self.assertEqual(self.count_rows("study_tasks"), 1)
            self.assertEqual(first.status, "success")
            self.assertEqual(second.status, "idempotent")

        self.run_in_db(scenario)

    def test_same_content_different_user_event_id_executes_separately(self):
        def scenario(settings):
            session_id = ChatRepository().create_session("chat")
            dispatcher = OnlineActionDispatcher(settings=settings)
            decision = Router().route("帮我创建一个15分钟数学任务")
            raw_events = RawEventRepository()
            event_id_a = raw_events.create(
                content="帮我创建一个15分钟数学任务",
                role="user",
                session_id=session_id,
                source_type="chat_message",
            )
            event_id_b = raw_events.create(
                content="帮我创建一个15分钟数学任务",
                role="user",
                session_id=session_id,
                source_type="chat_message",
            )

            dispatcher.dispatch(
                decision=decision,
                user_input="帮我创建一个15分钟数学任务",
                session_id=session_id,
                user_event_id=event_id_a,
            )
            dispatcher.dispatch(
                decision=decision,
                user_input="帮我创建一个15分钟数学任务",
                session_id=session_id,
                user_event_id=event_id_b,
            )

            self.assertEqual(self.count_rows("study_tasks"), 2)

        self.run_in_db(scenario)

    def test_chat_planning_request_creates_study_task(self):
        def scenario(settings):
            session_id = ChatRepository().create_session("chat")
            result = OnlineSessionWorkflow(settings=settings).handle_user_message(
                session_id=session_id,
                user_input="帮我创建一个15分钟数学任务",
            )

            with closing(database.get_connection()) as connection:
                task = connection.execute(
                    "SELECT title, subject, estimated_minutes, source, status FROM study_tasks"
                ).fetchone()

            self.assertEqual(result.router_decision.route, "planning")
            self.assertIn("已加入今日任务", result.assistant_text)
            self.assertEqual(task["title"], "数学任务")
            self.assertEqual(task["subject"], "数学")
            self.assertEqual(task["estimated_minutes"], 15)
            self.assertEqual(task["source"], "chat")
            self.assertEqual(task["status"], "todo")

        self.run_in_db(scenario)

    def test_chat_practice_review_question_answers_and_creates_pending_card(self):
        def scenario(settings):
            session_id = ChatRepository().create_session("chat")
            result = OnlineSessionWorkflow(settings=settings).handle_user_message(
                session_id=session_id,
                user_input="sin2x 积分我不会，原因是不会换元，科目数学，章节积分",
            )

            with closing(database.get_connection()) as connection:
                card_count = int(connection.execute("SELECT COUNT(*) FROM mistake_cards").fetchone()[0])
                pending = connection.execute(
                    "SELECT status, action_type, payload_json FROM pending_actions"
                ).fetchone()
                steps = connection.execute(
                    """
                    SELECT step_type
                    FROM agent_trace_steps
                    WHERE agent_run_id = ?
                    ORDER BY step_order ASC
                    """,
                    (result.agent_run_id,),
                ).fetchall()

            self.assertEqual(result.router_decision.route, "practice_review")
            self.assertIn("换元", result.assistant_text)
            self.assertIn("建议保存为错题卡", result.assistant_text)
            self.assertEqual(card_count, 0)
            self.assertEqual(pending["status"], "pending_confirmation")
            self.assertEqual(pending["action_type"], "create_review_card")
            self.assertEqual(result.action_result["intent"], "answer_first_then_suggest")
            self.assertIn("action_intent", [row["step_type"] for row in steps])
            self.assertIn("action_dispatch", [row["step_type"] for row in steps])

        self.run_in_db(scenario)

    def test_explicit_practice_review_command_creates_mistake_card(self):
        def scenario(settings):
            session_id = ChatRepository().create_session("chat")
            result = OnlineSessionWorkflow(settings=settings).handle_user_message(
                session_id=session_id,
                user_input="帮我生成错题卡：sin2x 积分我不会，原因是不会换元，科目数学，章节积分",
            )

            with closing(database.get_connection()) as connection:
                card = connection.execute(
                    "SELECT subject, chapter, question, mistake_reason FROM mistake_cards"
                ).fetchone()

            self.assertEqual(result.router_decision.route, "practice_review")
            self.assertIn("已生成错题卡", result.assistant_text)
            self.assertEqual(card["subject"], "数学")
            self.assertEqual(card["chapter"], "积分")
            self.assertIn("sin2x", card["question"])

        self.run_in_db(scenario)

    def test_pending_action_save_and_dismiss_are_idempotent(self):
        def scenario(settings):
            session_id = ChatRepository().create_session("chat")
            workflow = OnlineSessionWorkflow(settings=settings)
            result = workflow.handle_user_message(
                session_id=session_id,
                user_input="sin2x 积分我不会，原因是不会换元，科目数学，章节积分",
            )
            pending_id = int(result.pending_action["id"])

            first = workflow.confirm_pending_action(pending_id, "save")
            second = workflow.confirm_pending_action(pending_id, "save")
            with closing(database.get_connection()) as connection:
                card_count = int(connection.execute("SELECT COUNT(*) FROM mistake_cards").fetchone()[0])
                completed = connection.execute(
                    "SELECT status, created_target_id FROM pending_actions WHERE id = ?",
                    (pending_id,),
                ).fetchone()

            self.assertTrue(first["ok"])
            self.assertTrue(second["ok"])
            self.assertEqual(card_count, 1)
            self.assertEqual(completed["status"], "completed")
            self.assertIsNotNone(completed["created_target_id"])

            result_2 = workflow.handle_user_message(
                session_id=session_id,
                user_input="这题要不要记错题：极限不会判断等价无穷小，原因是方法不会迁移，科目数学，章节极限",
            )
            workflow.confirm_pending_action(int(result_2.pending_action["id"]), "dismiss")
            with closing(database.get_connection()) as connection:
                card_count_after_dismiss = int(connection.execute("SELECT COUNT(*) FROM mistake_cards").fetchone()[0])
                dismissed = connection.execute(
                    "SELECT status FROM pending_actions WHERE id = ?",
                    (int(result_2.pending_action["id"]),),
                ).fetchone()

            self.assertEqual(card_count_after_dismiss, 1)
            self.assertEqual(dismissed["status"], "dismissed")

        self.run_in_db(scenario)

    def test_mistake_review_repositories_share_one_formal_pool(self):
        def scenario(settings):
            PracticeReviewRepository().create_card(
                subject="数学",
                chapter="积分",
                question="sin2x 积分",
                analysis="换元法薄弱",
                mistake_reason="method_gap",
                knowledge_points="积分换元",
                review_priority=4,
            )
            cards = MistakeReviewRepository().list_cards(limit=10)
            with closing(database.get_connection()) as connection:
                practice_review_count = int(
                    connection.execute("SELECT COUNT(*) FROM practice_reviews").fetchone()[0]
                )

            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["question"], "sin2x 积分")
            self.assertEqual(practice_review_count, 0)

        self.run_in_db(scenario)

    def test_focus_invalid_state_safe_methods_and_ui_controls(self):
        workflow = FocusWorkflow()
        session_state = {
            "focus_timer_state": FocusTimerState(
                task_title="数学积分练习",
                status=FocusTimerStatus.RUNNING,
            ).model_dump()
        }

        resume_result = workflow.safe_resume_timer(session_state)
        self.assertFalse(resume_result["ok"])
        self.assertIn("无需继续", resume_result["message"])
        self.assertEqual(get_visible_timer_controls(FocusTimerStatus.RUNNING), ["pause", "end"])
        self.assertEqual(get_visible_timer_controls(FocusTimerStatus.PAUSED), ["resume", "end"])
        self.assertEqual(get_visible_timer_controls(FocusTimerStatus.IDLE), ["start"])

    def test_vision_fallback_does_not_call_image_url_for_deepseek_flash(self):
        settings = Settings("", None, "deepseek-v4-flash")
        self.assertFalse(supports_vision_model(settings))
        agent = FocusSupervisionAgent(settings)
        with patch(
            "kaoyan_agent.agents.focus_supervision_agent.run_structured_vision_agent",
            side_effect=AssertionError("vision call should not happen"),
        ):
            result = agent.recognize_snapshot(b"not-real-image", mime_type="image/png")

        self.assertEqual(result["state_type"], "unknown")
        self.assertEqual(result["recognition_source"], "manual_fallback")
        self.assertIn("generation_error", result)

    def test_local_yolo_missing_weights_is_friendly_unavailable(self):
        recognizer = LocalYoloFocusRecognizer(Path("missing-focus-model.pt"))

        self.assertFalse(recognizer.is_available())
        result = recognizer.predict_frame(None)
        self.assertEqual(result.label, "unknown")
        self.assertEqual(result.label_text, "无法判断")
        self.assertIn("status", result.debug)

    def test_focus_state_event_debounce_skips_repeated_state(self):
        def scenario(settings):
            workflow = FocusWorkflow()
            session_id = workflow.start_focus_session(task_id=None, planned_minutes=25)
            first = workflow.record_focus_state(
                session_id,
                "focused",
                confidence=0.8,
                explanation="local yolo",
                metadata={"recognition_source": "local_yolo"},
            )
            second = workflow.record_focus_state(
                session_id,
                "focused",
                confidence=0.81,
                explanation="local yolo",
                metadata={"recognition_source": "local_yolo"},
            )
            with closing(database.get_connection()) as connection:
                count = int(connection.execute("SELECT COUNT(*) FROM focus_state_events").fetchone()[0])

            self.assertEqual(first["status"], "recorded")
            self.assertEqual(second["status"], "skipped")
            self.assertEqual(count, 1)

        self.run_in_db(scenario)

    def test_memory_backend_audit_reports_configured_chroma_and_neo4j_status(self):
        def scenario(settings):
            audit = MemoryBackendAudit(settings=settings).run()

            self.assertEqual(audit["vector_backend_type"], "chroma")
            self.assertTrue(audit["vector_backend_enabled"])
            self.assertIn("raw_events", audit["counts"])
            self.assertEqual(audit["graph_backend_type"], "neo4j")
            self.assertFalse(audit["graph_backend_connected"])
            self.assertTrue(audit["graph"]["error"])

        self.run_in_db(scenario)

    def test_ui_modules_import(self):
        import kaoyan_agent.ui.task_page  # noqa: F401
        import kaoyan_agent.ui.fortune_page  # noqa: F401
        import kaoyan_agent.ui.mistake_review_page  # noqa: F401
        import kaoyan_agent.ui.supervision_page  # noqa: F401
        import kaoyan_agent.ui.agent_trace_page  # noqa: F401
        import kaoyan_agent.ui.memory_system_page  # noqa: F401

    def test_init_db_upgrades_legacy_focus_sessions_without_timer_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = make_settings(temp_dir)
            with closing(sqlite3.connect(db_path)) as connection:
                connection.execute(
                    """
                    CREATE TABLE focus_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project_id INTEGER,
                        task_id INTEGER,
                        task_title TEXT NOT NULL DEFAULT '',
                        subject TEXT NOT NULL DEFAULT '',
                        planned_minutes INTEGER NOT NULL DEFAULT 0,
                        actual_seconds INTEGER NOT NULL DEFAULT 0,
                        actual_minutes INTEGER NOT NULL DEFAULT 0,
                        pause_count INTEGER NOT NULL DEFAULT 0,
                        completion_status TEXT NOT NULL DEFAULT 'unknown',
                        reflection TEXT NOT NULL DEFAULT '',
                        started_at TEXT,
                        ended_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
                connection.commit()

            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                with closing(database.get_connection()) as connection:
                    columns = {
                        row["name"]
                        for row in connection.execute("PRAGMA table_info(focus_sessions)")
                    }
                    indexes = {
                        row["name"]
                        for row in connection.execute("PRAGMA index_list(focus_sessions)")
                    }

            self.assertIn("timer_status", columns)
            self.assertIn("segment_started_at", columns)
            self.assertIn("accumulated_seconds", columns)
            self.assertIn("idx_focus_sessions_timer_status", indexes)


if __name__ == "__main__":
    unittest.main()
