import tempfile
import sys
import types
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import Mock, patch

from kaoyan_agent.agents.focus_supervision_agent import FocusSupervisionAgent
from kaoyan_agent.core.settings import Settings
from kaoyan_agent.db import database
from kaoyan_agent.services.local_yolo_focus_recognizer import (
    LocalYoloFocusRecognizer,
    diagnose_camera_access,
    find_yolo_weight_candidates,
)
from kaoyan_agent.ui.components import pomodoro_supervision_panel
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
        agent = FocusSupervisionAgent(Settings("", None, "model"))
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
        self.assertEqual(result["focus_score"], 0)
        self.assertEqual(result["explanation"], "fallback")

    def test_fallback_report_counts_supervision_states(self):
        agent = FocusSupervisionAgent(Settings("", None, "model"))
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
        self.assertEqual(recognition["focus_score"], 91)
        self.assertEqual(report["focus_quality"], "stable")
        self.assertEqual(report["focus_score"], 92)
        self.assertEqual(
            [row["source_type"] for row in raw_events],
            ["focus_state_event", "focus_report"],
        )

    def test_camera_unavailable_does_not_block_timer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings("", None, "test-model", database_path=Path(temp_dir) / "app.db")
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                workflow = FocusWorkflow()
                with patch(
                    "kaoyan_agent.services.local_yolo_focus_recognizer.diagnose_camera_access",
                    return_value={"can_open": False, "error": "camera unavailable"},
                ):
                    session_id = workflow.start_focus_session(task_id=None, planned_minutes=25)

        self.assertTrue(session_id)


class LocalYoloFocusRecognizerTest(unittest.TestCase):
    def test_pt_file_is_scanned_from_models(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            model_dir = Path(temp_dir) / "models" / "focus"
            model_dir.mkdir(parents=True)
            weight = model_dir / "best.pt"
            weight.write_bytes(b"fake")

            candidates = find_yolo_weight_candidates(project_root=Path(temp_dir))

        self.assertIn(weight, candidates)

    def test_missing_weight_path_returns_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "models" / "missing.pt"
            recognizer = LocalYoloFocusRecognizer(
                missing,
                project_root=Path(temp_dir),
            )

        self.assertFalse(recognizer.is_available())
        self.assertEqual(recognizer.debug["status"], "weights_missing")
        self.assertIn("不存在", recognizer.debug["message"])

    def test_missing_cv2_and_ultralytics_return_clear_errors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            weight = Path(temp_dir) / "models" / "best.pt"
            weight.parent.mkdir(parents=True)
            weight.write_bytes(b"fake")

            def cv2_missing(name):
                if name == "cv2":
                    return None
                return object()

            with patch("kaoyan_agent.services.local_yolo_focus_recognizer.importlib.util.find_spec", cv2_missing):
                cv2_result = LocalYoloFocusRecognizer(weight, project_root=Path(temp_dir))

            def ultralytics_missing(name):
                if name == "ultralytics":
                    return None
                return object()

            with patch("kaoyan_agent.services.local_yolo_focus_recognizer.importlib.util.find_spec", ultralytics_missing):
                yolo_result = LocalYoloFocusRecognizer(weight, project_root=Path(temp_dir))

        self.assertEqual(cv2_result.debug["status"], "cv2_missing")
        self.assertEqual(yolo_result.debug["status"], "ultralytics_missing")

    def test_mock_yolo_predict_outputs_label_and_confidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            weight = Path(temp_dir) / "models" / "best.pt"
            weight.parent.mkdir(parents=True)
            weight.write_bytes(b"fake")

            class FakeBox:
                cls = [0]
                conf = [0.87]

            class FakeResult:
                names = {0: "reading"}
                boxes = [FakeBox()]

            class FakeModel:
                names = {0: "reading"}

                def predict(self, *args, **kwargs):
                    return [FakeResult()]

            with patch("kaoyan_agent.services.local_yolo_focus_recognizer.importlib.util.find_spec", return_value=object()):
                recognizer = LocalYoloFocusRecognizer(
                    weight,
                    project_root=Path(temp_dir),
                    yolo_factory=lambda path: FakeModel(),
                )
                result = recognizer.predict_frame(object())

        self.assertTrue(recognizer.is_available())
        self.assertEqual(result.label, "focused")
        self.assertEqual(result.confidence, 0.87)

    def test_camera_diagnostic_reports_unavailable_camera(self):
        fake_capture = Mock()
        fake_capture.isOpened.return_value = False
        fake_cv2 = types.SimpleNamespace(VideoCapture=Mock(return_value=fake_capture))
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            with patch("kaoyan_agent.services.local_yolo_focus_recognizer.module_available", return_value=True):
                diagnostic = diagnose_camera_access(99)

        self.assertFalse(diagnostic["can_open"])
        self.assertIn("摄像头无法打开", diagnostic["error"])


class FocusSupervisionUITest(unittest.TestCase):
    def test_supervision_ui_uses_realtime_camera_sampler_not_file_upload(self):
        source_path = Path(pomodoro_supervision_panel.__file__)
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("AutoFocusFrameProcessor", source)
        self.assertIn("webrtc_streamer", source)
        self.assertIn("render_auto_camera_sampler", source)
        self.assertIn("render_auto_camera_status", source)
        self.assertIn("find_yolo_weight_candidates", source)
        self.assertIn("latest_supervision_frame", source)
        self.assertIn("最近错误 / YOLO 诊断", source)
        self.assertNotIn("file_uploader", source)


if __name__ == "__main__":
    unittest.main()
