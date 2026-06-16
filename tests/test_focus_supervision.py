import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from kaoyan_agent.agents.focus_supervision_agent import FocusSupervisionAgent
from kaoyan_agent.core.settings import Settings
from kaoyan_agent.db import database
from kaoyan_agent.vision.focus_state_rules import FocusStateRuleEngine
from kaoyan_agent.workflows.focus import FocusWorkflow


class FakeSupervisionAgent:
    def recognize_snapshot(self, image_bytes, mime_type="image/png", context=""):
        return {
            "state_type": "focused",
            "confidence": 0.91,
            "explanation": "user appears to be studying",
        }

    def generate_report(self, session, state_events, timeline_events=None):
        return {
            "focus_score": 92,
            "effective_focus_minutes": 20,
            "away_count": 0,
            "distracted_count": 0,
            "blocked_count": 0,
            "longest_focus_minutes": 20,
            "focus_quality": "stable",
            "ai_summary": "The session stayed mostly focused.",
            "possible_problem_signal": "No strong problem signal.",
            "suggested_action": "Keep the same study block size.",
        }


class FocusSupervisionAgentTest(unittest.TestCase):
    def test_normalize_recognition_rejects_bad_state(self):
        agent = FocusSupervisionAgent()
        fallback = {
            "state_type": "unknown",
            "confidence": 0.0,
            "explanation": "fallback",
        }

        result = agent.normalize_recognition(
            {"state_type": "bad", "confidence": 3, "explanation": ""},
            fallback,
        )

        self.assertEqual(result["state_type"], "unknown")
        self.assertEqual(result["confidence"], 1.0)
        self.assertEqual(result["explanation"], "fallback")

    def test_fallback_report_counts_supervision_states(self):
        agent = FocusSupervisionAgent()
        report = agent.build_fallback_report(
            {"planned_minutes": 25, "actual_minutes": 20},
            [
                {"state_type": "focused"},
                {"state_type": "focused"},
                {"state_type": "away"},
                {"state_type": "distracted"},
            ],
        )

        self.assertEqual(report["effective_focus_minutes"], 10)
        self.assertEqual(report["focus_score"], 50)
        self.assertEqual(report["away_count"], 1)
        self.assertEqual(report["distracted_count"], 1)


class FocusStateRuleEngineTest(unittest.TestCase):
    def test_rule_engine_maps_study_behavior_to_focused(self):
        result = FocusStateRuleEngine().classify(
            [{"label": "reading", "confidence": 0.8}]
        )

        self.assertEqual(result.state_type, "focused")

    def test_rule_engine_maps_phone_to_distracted(self):
        result = FocusStateRuleEngine().classify(
            [{"label": "using_phone", "confidence": 0.82}]
        )

        self.assertEqual(result.state_type, "distracted")
        self.assertEqual(result.metrics["phone_count"], 1)

    def test_rule_engine_maps_standing_to_away(self):
        result = FocusStateRuleEngine().classify(
            [{"label": "standing", "confidence": 0.76}]
        )

        self.assertEqual(result.state_type, "away")

    def test_rule_engine_maps_empty_frame_to_away(self):
        result = FocusStateRuleEngine().classify([])

        self.assertEqual(result.state_type, "away")


class FocusWorkflowTest(unittest.TestCase):
    def test_camera_state_and_report_are_saved_as_raw_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                workflow = FocusWorkflow(supervision_agent=FakeSupervisionAgent())

                session_id = workflow.start_focus_session(
                    task_id=None,
                    planned_minutes=25,
                )
                recognition = workflow.recognize_camera_snapshot(
                    focus_session_id=session_id,
                    image_bytes=b"fake-image",
                    mime_type="image/png",
                    context="math review",
                )
                report_id = workflow.finish_focus_session(
                    focus_session_id=session_id,
                    actual_minutes=20,
                    pause_count=0,
                    completion_status="completed",
                    reflection="ok",
                )
                report = workflow.get_focus_report(report_id)

                with closing(database.get_connection()) as connection:
                    raw_events = connection.execute(
                        """
                        SELECT source_type, source_id
                        FROM raw_events
                        ORDER BY id ASC
                        """
                    ).fetchall()

        self.assertEqual(recognition["state_type"], "focused")
        self.assertEqual(report["focus_quality"], "stable")
        self.assertEqual(report["focus_score"], 92)
        self.assertEqual(
            [row["source_type"] for row in raw_events],
            ["focus_state_event", "focus_report"],
        )


if __name__ == "__main__":
    unittest.main()
