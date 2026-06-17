from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from kaoyan_agent.agents.motivation import MotivationAgent
from kaoyan_agent.agents.problem_discovery_agent import ProblemDiscoveryAgent
from kaoyan_agent.agents.router import Router
from kaoyan_agent.core.settings import Settings
from kaoyan_agent.db import database
from kaoyan_agent.repositories.conversation_repository import ChatRepository
from kaoyan_agent.repositories.motivation import MotivationRepository
from kaoyan_agent.repositories.study_tasks import StudyTaskRepository
from kaoyan_agent.schemas.focus import FocusTimerStatus
from kaoyan_agent.schemas.nightly_memory import NightlyMemoryUpdateOutput
from kaoyan_agent.schemas.study_task import DailyTaskCreate, DailyTaskStatus
from kaoyan_agent.workflows.chat_workflow import OnlineSessionWorkflow
from kaoyan_agent.workflows.focus import FocusWorkflow
from kaoyan_agent.workflows.planning import PlanningWorkflow


class FakeNightlyAgent:
    def __init__(self, result):
        self.result = result

    def run(self, **kwargs):
        return self.result


class FakeNightlyResult:
    def __init__(self, output, parse_status="success", error_message=""):
        self.output = output
        self.parse_status = parse_status
        self.error_message = error_message


class FakeMotivationAgent:
    def __init__(self, sign):
        self.sign = sign

    def generate_daily_sign(self):
        return self.sign


class FakeSupervisionAgent:
    def generate_report(self, session, state_events, timeline_events=None):
        return {
            "effective_focus_minutes": 1,
            "away_count": 0,
            "distracted_count": 0,
            "blocked_count": 0,
            "longest_focus_minutes": 1,
            "focus_quality": "stable",
            "ai_summary": "Timer session completed.",
            "possible_problem_signal": "No strong signal.",
            "suggested_action": "Keep the same block size.",
        }

    def recognize_snapshot(self, image_bytes, mime_type="image/png", context=""):
        return {
            "state_type": "focused",
            "confidence": 0.9,
            "explanation": "focused",
        }


def problem_output() -> NightlyMemoryUpdateOutput:
    return NightlyMemoryUpdateOutput.model_validate(
        {
            "daily_summary": "summary",
            "discovered_problems": [
                {
                    "problem_type": "execution_issue",
                    "subject": "math",
                    "description": "Stops reviewing mistakes before finishing.",
                    "evidence": ["raw evidence"],
                    "root_cause": "task too large",
                    "severity": 3,
                    "confidence": 0.8,
                    "value_score": 4,
                    "suggested_action": "Use a 10 minute review block.",
                    "status": "open",
                }
            ],
        }
    )


class FeatureCDEIntegrationTest(unittest.TestCase):
    def test_problem_discovery_only_returns_successful_parse_results(self):
        agent = ProblemDiscoveryAgent(
            nightly_agent=FakeNightlyAgent(FakeNightlyResult(problem_output()))
        )

        result = agent.discover([{"content": "evidence"}], review_date="2026-06-15")

        self.assertEqual(result.parse_status, "success")
        self.assertEqual(len(result.problems), 1)
        self.assertEqual(result.problems[0]["problem_type"], "execution_issue")

    def test_problem_discovery_failed_parse_returns_no_problems_with_error(self):
        fallback = NightlyMemoryUpdateOutput.model_validate(
            {"daily_summary": "fallback", "discovered_problems": []}
        )
        agent = ProblemDiscoveryAgent(
            nightly_agent=FakeNightlyAgent(
                FakeNightlyResult(fallback, parse_status="failed", error_message="bad json")
            )
        )

        result = agent.discover([{"content": "evidence"}], review_date="2026-06-15")

        self.assertEqual(result.problems, [])
        self.assertEqual(result.parse_status, "failed")
        self.assertIn("bad json", result.error_message)

    def test_router_recognizes_cde_feature_keywords(self):
        cases = {
            "抽签": "motivation",
            "上岸签": "motivation",
            "成绩趋势": "score_trend",
            "今日作战台": "planning",
            "开始番茄钟": "focus",
            "专注统计": "focus",
            "错题卡": "practice_review",
        }
        router = Router()

        for text, expected_route in cases.items():
            with self.subTest(text=text):
                self.assertEqual(router.route(text).route, expected_route)

    def test_motivation_chinese_sign_level_is_mapped_and_persisted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings("", None, "test-model", database_path=Path(temp_dir) / "app.db")
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                fallback = {
                    "sign_level": "steady",
                    "sign_text": "fallback",
                    "today_advice": "fallback advice",
                    "action": "fallback action",
                }
                sign = MotivationAgent(settings).normalize_sign(
                    {
                        "sign_level": "上上签",
                        "sign_text": "稳住节奏",
                        "today_advice": "先完成一个小任务",
                        "action": "复盘一道错题",
                    },
                    fallback,
                )
                workflow = PlanningWorkflow(settings)
                workflow.motivation_agent = FakeMotivationAgent(sign)

                result = workflow.generate_daily_sign()
                items = MotivationRepository().list_items(limit=10)

        self.assertEqual(result["sign_level"], "top")
        self.assertEqual(items[0]["sign_level"], "top")
        self.assertEqual(items[0]["sign_type"], "daily_sign")

    def test_study_task_repository_centralizes_daily_status_mapping(self):
        self.assertEqual(
            StudyTaskRepository.to_study_status(DailyTaskStatus.PENDING),
            "todo",
        )
        self.assertEqual(
            StudyTaskRepository.to_study_status(DailyTaskStatus.IN_PROGRESS),
            "doing",
        )
        self.assertEqual(
            StudyTaskRepository.to_study_status(DailyTaskStatus.DONE),
            "done",
        )

    def test_focus_timer_lifecycle_preserves_report_and_raw_event_chain(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings("", None, "test-model", database_path=Path(temp_dir) / "app.db")
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                task_repository = StudyTaskRepository()
                task = task_repository.create_daily_task(
                    DailyTaskCreate(
                        subject="math",
                        task="review limits",
                        reason="weak point",
                        estimated_minutes=1,
                    ),
                    scheduled_date=datetime.now().date().isoformat(),
                )
                workflow = FocusWorkflow(
                    task_repository=task_repository,
                    supervision_agent=FakeSupervisionAgent(),
                )
                session_state = {}

                prepared = workflow.prepare_timer_from_task(session_state, task.id)
                self.assertEqual(prepared.status, FocusTimerStatus.IDLE)
                running = workflow.start_timer(session_state)
                running.segment_started_at = (
                    datetime.now(timezone.utc) - timedelta(seconds=61)
                ).isoformat()
                workflow.save_timer_state(session_state, running)
                paused = workflow.pause_timer(session_state)
                self.assertEqual(paused.status, FocusTimerStatus.PAUSED)
                resumed = workflow.resume_timer(session_state)
                self.assertEqual(resumed.status, FocusTimerStatus.RUNNING)
                result = workflow.end_timer(session_state, reflection="ok")

                task_after = task_repository.get(task.id)
                stats = workflow.get_stats()
                with closing(database.get_connection()) as connection:
                    raw_events = connection.execute(
                        "SELECT source_type FROM raw_events ORDER BY id ASC"
                    ).fetchall()

        self.assertTrue(result["completed"])
        self.assertEqual(task_after["status"], "done")
        self.assertGreaterEqual(stats["total_sessions"], 1)
        self.assertIn("focus_report", [row["source_type"] for row in raw_events])

    def test_online_session_guides_page_oriented_focus_request(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings("", None, "test-model", database_path=Path(temp_dir) / "app.db")
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                session_id = ChatRepository().create_session("chat")
                result = OnlineSessionWorkflow(settings=settings).handle_user_message(
                    session_id=session_id,
                    user_input="开始番茄钟",
                )

        self.assertEqual(result.router_decision.route, "focus")
        self.assertIn("督学模式", result.assistant_text)
        self.assertIn("番茄钟", result.assistant_text)


if __name__ == "__main__":
    unittest.main()
