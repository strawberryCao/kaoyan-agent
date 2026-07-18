import os
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
    FocusRecognitionResult,
    LocalYoloFocusRecognizer,
    diagnose_camera_access,
    find_yolo_weight_candidates,
    configure_yolo_runtime_dir,
)
from kaoyan_agent.services.focus_report_calculator import calculate_focus_report
from kaoyan_agent.services.focus_temporal_tracker import DETECTOR_VERSION, FocusTemporalTracker
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
                {"state_type": "focused", "observed_seconds": 300},
                {"state_type": "focused", "observed_seconds": 300},
                {"state_type": "away", "observed_seconds": 300},
                {"state_type": "distracted", "observed_seconds": 300},
            ],
        )

        self.assertEqual(report["effective_focus_minutes"], 10)
        self.assertEqual(report["focus_score"], 50)
        self.assertEqual(report["away_count"], 1)
        self.assertEqual(report["distracted_count"], 1)
        self.assertEqual(report["evidence_status"], "sufficient")


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

    def test_rule_engine_maps_empty_frame_to_unknown(self):
        result = FocusStateRuleEngine().classify([])

        self.assertEqual(result.state_type, "unknown")


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
                workflow.record_focus_state(
                    focus_session_id=session_id,
                    state_type="focused",
                    confidence=0.91,
                    observed_seconds=1200,
                    detector_version=DETECTOR_VERSION,
                    force=True,
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
        self.assertEqual(report["focus_score"], 100)
        self.assertEqual(report["monitored_seconds"], 1200)
        self.assertEqual(
            [row["source_type"] for row in raw_events],
            ["focus_state_event", "focus_state_event", "focus_report"],
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

    def test_ended_session_rejects_late_camera_writes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings("", None, "test-model", database_path=Path(temp_dir) / "app.db")
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                workflow = FocusWorkflow(supervision_agent=FakeSupervisionAgent())
                session_id = workflow.start_focus_session(task_id=None, planned_minutes=1)
                workflow.finish_focus_session(
                    focus_session_id=session_id,
                    actual_minutes=1,
                    actual_seconds=60,
                    pause_count=0,
                    completion_status="completed",
                )
                result = workflow.record_focus_state(
                    focus_session_id=session_id,
                    state_type="away",
                    confidence=1.0,
                    observed_seconds=10,
                    force=True,
                )
                events = workflow.focus_repository.list_state_events(session_id)

        self.assertEqual(result["status"], "rejected")
        self.assertEqual(events, [])


class LocalYoloFocusRecognizerTest(unittest.TestCase):
    def test_yolo_runtime_dir_uses_writable_data_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            with patch(
                "kaoyan_agent.services.local_yolo_focus_recognizer.DATA_DIR",
                data_dir,
            ):
                with patch.dict(os.environ, {}, clear=True):
                    result = configure_yolo_runtime_dir()
                    configured = os.environ.get("YOLO_CONFIG_DIR")
                    exists = result.is_dir()

        self.assertEqual(result, data_dir / "ultralytics")
        self.assertEqual(configured, str(result.resolve()))
        self.assertTrue(exists)

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
                names = {0: "person", 67: "cell phone"}
                boxes = [FakeBox()]

            class FakeModel:
                names = {0: "person", 67: "cell phone"}

                def predict(self, *args, **kwargs):
                    return [FakeResult()]

            with patch("kaoyan_agent.services.local_yolo_focus_recognizer.importlib.util.find_spec", return_value=object()):
                recognizer = LocalYoloFocusRecognizer(
                    None,
                    person_weights_path=weight,
                    project_root=Path(temp_dir),
                    yolo_factory=lambda path: FakeModel(),
                    evidence_extractor=lambda frame: {
                        "source": "test",
                        "face_visible": True,
                        "head_centered": True,
                        "visual_evidence_score": 0.78,
                        "focus_ready": True,
                    },
                )
                result = recognizer.predict_frame(object())

        self.assertTrue(recognizer.is_available())
        self.assertEqual(result.label, "focused")
        self.assertEqual(result.confidence, 0.78)

    def test_no_behavior_detection_is_unknown_not_away(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            weight = Path(temp_dir) / "models" / "best.pt"
            weight.parent.mkdir(parents=True)
            weight.write_bytes(b"fake")

            class FakeResult:
                names = {0: "person", 67: "cell phone"}
                boxes = []

            class FakeModel:
                names = {0: "person", 67: "cell phone"}

                def predict(self, *args, **kwargs):
                    return [FakeResult()]

            with patch("kaoyan_agent.services.local_yolo_focus_recognizer.importlib.util.find_spec", return_value=object()):
                recognizer = LocalYoloFocusRecognizer(
                    None,
                    person_weights_path=weight,
                    project_root=Path(temp_dir),
                    yolo_factory=lambda path: FakeModel(),
                )
                result = recognizer.predict_frame(object())

        self.assertEqual(result.label, "unknown")

    def test_phone_detection_has_priority_over_focus_evidence(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            weight = Path(temp_dir) / "models" / "best.pt"
            weight.parent.mkdir(parents=True)
            weight.write_bytes(b"fake")

            class PersonBox:
                cls = [0]
                conf = [0.95]

            class PhoneBox:
                cls = [67]
                conf = [0.7]

            class FakeResult:
                names = {0: "person", 67: "cell phone"}
                boxes = [PersonBox(), PhoneBox()]

            class FakeModel:
                names = {0: "person", 67: "cell phone"}

                def predict(self, *args, **kwargs):
                    return [FakeResult()]

            with patch("kaoyan_agent.services.local_yolo_focus_recognizer.importlib.util.find_spec", return_value=object()):
                recognizer = LocalYoloFocusRecognizer(
                    None,
                    person_weights_path=weight,
                    project_root=Path(temp_dir),
                    yolo_factory=lambda path: FakeModel(),
                    evidence_extractor=lambda frame: {
                        "source": "test",
                        "face_visible": True,
                        "head_centered": True,
                        "visual_evidence_score": 0.9,
                        "focus_ready": True,
                    },
                )
                result = recognizer.predict_frame(object())

        self.assertEqual(result.label, "distracted")
        self.assertEqual(result.confidence, 0.7)
        self.assertTrue(result.phone_present)

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
    def test_camera_browser_access_allows_secure_and_loopback_urls(self):
        allowed_urls = [
            "https://study.example.com/supervision",
            "http://localhost:8501",
            "http://camera.localhost:8501",
            "http://127.0.0.1:8501",
            "http://[::1]:8501",
        ]

        for url in allowed_urls:
            with self.subTest(url=url):
                self.assertEqual(
                    pomodoro_supervision_panel.camera_browser_access_issue(url),
                    "",
                )

    def test_camera_browser_access_rejects_insecure_remote_http_url(self):
        issue = pomodoro_supervision_panel.camera_browser_access_issue(
            "http://192.168.1.23:8501/supervision"
        )

        self.assertIn("HTTPS", issue)
        self.assertIn("localhost", issue)
        self.assertIn("192.168.1.23", issue)

    def test_supervision_ui_uses_realtime_camera_sampler_not_file_upload(self):
        source_path = Path(pomodoro_supervision_panel.__file__)
        source = source_path.read_text(encoding="utf-8")

        self.assertIn("AutoFocusFrameProcessor", source)
        self.assertIn("webrtc_streamer", source)
        self.assertIn("render_auto_camera_sampler", source)
        self.assertIn("render_auto_camera_status", source)
        self.assertIn("camera_browser_access_issue", source)
        self.assertIn("find_yolo_weight_candidates", source)
        self.assertIn("latest_supervision_frame", source)
        self.assertIn("FocusTemporalTracker", source)
        self.assertIn("摄像头预览仍会开启", source)
        self.assertNotIn("elif camera_enabled and not available", source)
        self.assertNotIn("最近错误 / YOLO 诊断", source)
        self.assertNotIn("file_uploader", source)


class FocusTemporalTrackerTest(unittest.TestCase):
    def test_away_requires_ten_continuous_seconds_without_person(self):
        tracker = FocusTemporalTracker(away_confirm_seconds=10, behavior_window_seconds=3)
        absent = FocusRecognitionResult(person_present=False)

        self.assertEqual(tracker.observe(absent, 0).observation.state_type, "unknown")
        self.assertEqual(tracker.observe(absent, 9).observation.state_type, "unknown")
        result = tracker.observe(absent, 10)

        self.assertEqual(result.observation.state_type, "away")
        self.assertEqual(result.observation.absence_seconds, 10)

    def test_person_return_resets_away_confirmation(self):
        tracker = FocusTemporalTracker(away_confirm_seconds=10, behavior_window_seconds=3)
        absent = FocusRecognitionResult(person_present=False)
        present = FocusRecognitionResult(person_present=True, label="unknown")

        tracker.observe(absent, 0)
        tracker.observe(absent, 8)
        returned = tracker.observe(present, 9)
        after_new_gap = tracker.observe(absent, 10)

        self.assertEqual(returned.observation.absence_seconds, 0)
        self.assertNotEqual(after_new_gap.observation.state_type, "away")

    def test_two_phone_observations_stabilize_as_distracted(self):
        tracker = FocusTemporalTracker(away_confirm_seconds=10, behavior_window_seconds=3)
        phone = FocusRecognitionResult(
            label="distracted",
            confidence=0.8,
            person_present=True,
        )

        tracker.observe(phone, 0)
        result = tracker.observe(phone, 1)

        self.assertEqual(result.observation.state_type, "distracted")


class FocusReportCalculatorTest(unittest.TestCase):
    def test_low_coverage_is_not_extrapolated_to_whole_session(self):
        report = calculate_focus_report(
            {"actual_seconds": 1200},
            [{"state_type": "focused", "observed_seconds": 60}],
        )

        self.assertEqual(report["effective_focus_minutes"], 1)
        self.assertEqual(report["coverage_ratio"], 0.05)
        self.assertEqual(report["evidence_status"], "insufficient")

    def test_report_counts_away_episodes_not_heartbeats(self):
        report = calculate_focus_report(
            {"actual_seconds": 40},
            [
                {"state_type": "away", "observed_seconds": 10},
                {"state_type": "away", "observed_seconds": 10},
                {"state_type": "focused", "observed_seconds": 10},
                {"state_type": "away", "observed_seconds": 10},
            ],
        )

        self.assertEqual(report["away_count"], 2)


if __name__ == "__main__":
    unittest.main()
