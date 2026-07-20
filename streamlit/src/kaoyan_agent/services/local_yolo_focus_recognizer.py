from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from kaoyan_agent.core.paths import DATA_DIR, PROJECT_ROOT
from kaoyan_agent.services.focus_temporal_tracker import DETECTOR_VERSION


LABEL_TEXT = {
    "focused": "专注",
    "distracted": "分心",
    "away": "离开",
    "unknown": "无法判断",
}

# Legacy SCB behavior labels. They are kept for diagnostics/tests, but the
# default runtime no longer uses the pilot behavior detector for decisions.
FOCUSED_BEHAVIORS = {"reading", "writing", "leaning_over_table"}
DISTRACTED_BEHAVIORS = {"using_phone", "phone", "cell_phone"}
UNKNOWN_BEHAVIORS = {"hand_raising", "bowing_head"}
EXPECTED_BEHAVIOR_LABELS = FOCUSED_BEHAVIORS | DISTRACTED_BEHAVIORS | UNKNOWN_BEHAVIORS
PERSON_LABELS = {"person"}
PHONE_LABELS = {"cell_phone", "mobile_phone", "phone"}
SCAN_DIRS = ("models", "weights", "runs", "src")


def configure_yolo_runtime_dir() -> Path:
    config_dir = DATA_DIR / "ultralytics"
    config_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(config_dir.resolve()))
    return config_dir


@dataclass
class FocusRecognitionResult:
    label: str = "unknown"
    label_text: str = "无法判断"
    confidence: float = 0.0
    person_present: Optional[bool] = None
    phone_present: Optional[bool] = None
    phone_confidence: float = 0.0
    face_visible: Optional[bool] = None
    head_centered: Optional[bool] = None
    pose_visible: Optional[bool] = None
    visual_evidence_score: float = 0.0
    behavior_labels: List[str] = field(default_factory=list)
    evidence_labels: List[str] = field(default_factory=list)
    reason: str = "视觉证据不足。"
    detector_version: str = DETECTOR_VERSION
    debug: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def resolve_candidate_path(value: Path | str, project_root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


def find_yolo_weight_candidates(
    configured_path: Optional[Path | str] = None,
    project_root: Optional[Path] = None,
    *,
    include_person_weights: bool = False,
) -> List[Path]:
    """Find legacy behavior weights while keeping the COCO evidence model separate."""

    root = Path(project_root or PROJECT_ROOT)
    candidates: list[Path] = []
    if configured_path:
        candidates.append(resolve_candidate_path(configured_path, root))

    for dirname in SCAN_DIRS:
        directory = root / dirname
        if directory.exists():
            candidates.extend(directory.rglob("*.pt"))
    candidates.extend(root.glob("*.pt"))

    unique: dict[str, Path] = {}
    for candidate in candidates:
        if not include_person_weights and "person_presence" in candidate.parts:
            continue
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        unique[key] = candidate

    return sorted(
        unique.values(),
        key=lambda path: (
            0 if path.exists() else 1,
            -path.stat().st_size if path.exists() else 0,
            str(path).lower(),
        ),
    )


def diagnose_camera_access(camera_id: int = 0) -> Dict[str, Any]:
    status = {
        "camera_id": int(camera_id),
        "cv2_importable": module_available("cv2"),
        "can_open": False,
        "error": "",
    }
    if not status["cv2_importable"]:
        status["error"] = "cv2 未安装，无法检查摄像头。"
        return status
    try:
        import cv2

        capture = cv2.VideoCapture(int(camera_id))
        try:
            status["can_open"] = bool(capture.isOpened())
            if not status["can_open"]:
                status["error"] = "摄像头无法打开，请检查 camera_id 或系统权限。"
        finally:
            capture.release()
    except Exception as exc:
        status["error"] = f"摄像头检查失败：{exc}"
    return status


class LocalYoloFocusRecognizer:
    """Zero-label evidence recognizer: COCO person/phone plus local visual cues."""

    def __init__(
        self,
        weights_path: Optional[Path | str],
        confidence_threshold: float = 0.5,
        *,
        person_weights_path: Optional[Path | str] = None,
        person_confidence_threshold: float = 0.35,
        phone_confidence_threshold: float = 0.35,
        visual_evidence_threshold: float = 0.55,
        presence_focus_confidence_threshold: float = 0.65,
        project_root: Optional[Path] = None,
        camera_id: int = 0,
        yolo_factory: Optional[Callable[[str], Any]] = None,
        person_yolo_factory: Optional[Callable[[str], Any]] = None,
        evidence_extractor: Optional[Callable[[Any], Dict[str, Any]]] = None,
        enable_mediapipe: bool = True,
        use_opencv_face_fallback: bool = True,
        check_camera: bool = False,
    ):
        self.project_root = Path(project_root or PROJECT_ROOT)
        self.configured_weights_path = Path(weights_path) if weights_path else None
        self.configured_person_weights_path = Path(person_weights_path) if person_weights_path else None
        self.confidence_threshold = max(0.0, min(1.0, confidence_threshold))
        self.person_confidence_threshold = max(0.0, min(1.0, person_confidence_threshold))
        self.phone_confidence_threshold = max(0.0, min(1.0, phone_confidence_threshold))
        self.visual_evidence_threshold = max(0.0, min(1.0, visual_evidence_threshold))
        self.presence_focus_confidence_threshold = max(
            0.0,
            min(1.0, presence_focus_confidence_threshold),
        )
        self.camera_id = int(camera_id)
        self._coco_model = None
        self._behavior_model = None
        self._person_model = None
        self._model = None  # Compatibility for existing diagnostics.
        self._person_class_ids: list[int] = []
        self._phone_class_ids: list[int] = []
        self._yolo_factory = person_yolo_factory or yolo_factory
        self._legacy_yolo_factory = yolo_factory
        self._evidence_extractor = evidence_extractor
        self._mp_face_mesh = None
        self._mp_pose = None
        self._mp_hands = None
        self._opencv_face_cascade = None
        self._enable_mediapipe = bool(enable_mediapipe)
        self._use_opencv_face_fallback = bool(use_opencv_face_fallback)
        self.weight_candidates = find_yolo_weight_candidates(
            self.configured_weights_path,
            self.project_root,
        )
        self.weights_path = self.resolve_weights_path()
        self.person_weights_path = (
            resolve_candidate_path(self.configured_person_weights_path, self.project_root)
            if self.configured_person_weights_path
            else None
        )
        self.debug: Dict[str, Any] = {
            "detector_version": DETECTOR_VERSION,
            "camera_id": self.camera_id,
            "cv2_importable": module_available("cv2"),
            "ultralytics_importable": module_available("ultralytics"),
            "mediapipe_importable": module_available("mediapipe"),
            "streamlit_webrtc_importable": module_available("streamlit_webrtc"),
            "behavior": {
                "configured_weights_path": str(self.configured_weights_path or ""),
                "weights_found": bool(self.weight_candidates),
                "weight_candidates": [str(path) for path in self.weight_candidates],
                "weights_path": str(self.weights_path or ""),
                "confidence_threshold": self.confidence_threshold,
                "model_loaded": False,
                "model_names": {},
                "status": "legacy_disabled",
                "last_inference_error": "",
            },
            "coco": {
                "weights_path": str(self.person_weights_path or ""),
                "person_confidence_threshold": self.person_confidence_threshold,
                "phone_confidence_threshold": self.phone_confidence_threshold,
                "presence_focus_confidence_threshold": self.presence_focus_confidence_threshold,
                "model_loaded": False,
                "model_names": {},
                "person_class_ids": [],
                "phone_class_ids": [],
                "sha256": self.file_sha256(self.person_weights_path),
                "last_inference_error": "",
            },
            "mediapipe": {
                "enabled": self._enable_mediapipe,
                "importable": module_available("mediapipe"),
                "model_loaded": False,
                "status": "not_loaded",
                "error": "",
            },
            "opencv_face": {
                "enabled": self._use_opencv_face_fallback,
                "model_loaded": False,
                "status": "not_loaded",
                "error": "",
            },
        }
        self.debug["person"] = self.debug["coco"]
        if check_camera:
            self.debug["camera"] = diagnose_camera_access(self.camera_id)
        self._load_models()
        self._load_visual_extractors()
        self._sync_legacy_debug_fields()

    def is_available(self) -> bool:
        return self._coco_model is not None

    def is_fully_available(self) -> bool:
        return (
            self._coco_model is not None
            and bool(self._person_class_ids)
            and bool(self._phone_class_ids)
            and self.visual_evidence_available()
        )

    def available(self) -> bool:
        return self.is_available()

    def full_available(self) -> bool:
        return self.is_fully_available()

    def visual_evidence_available(self) -> bool:
        return bool(
            self._evidence_extractor
            or self._mp_face_mesh
            or self._mp_pose
            or self._opencv_face_cascade
        )

    def status_message(self) -> str:
        if self.is_fully_available():
            return "COCO 人体/手机检测和本地视觉证据（MediaPipe 或 OpenCV）均可用。"
        if self._coco_model is not None and not self.visual_evidence_available():
            return "COCO 人体/手机检测可用；脸部、姿态或人脸兜底证据不可用，只能降级判断人在、离开和手机分心。"
        if self._coco_model is not None:
            return "COCO 检测可用但类别不完整，请检查 person/cell phone 类别。"
        return str(self.debug.get("message") or "本地视觉证据模型不可用。")

    def resolve_weights_path(self) -> Optional[Path]:
        if self.configured_weights_path:
            return resolve_candidate_path(self.configured_weights_path, self.project_root)
        return next((path for path in self.weight_candidates if path.exists()), None)

    def predict_frame(self, frame) -> FocusRecognitionResult:
        if not self.is_available():
            return FocusRecognitionResult(debug={**self.debug, "status": "unavailable"})

        class_filter = sorted(set(self._person_class_ids + self._phone_class_ids))
        detections = self._predict_model(
            self._coco_model,
            frame,
            min(self.person_confidence_threshold, self.phone_confidence_threshold),
            "coco",
            classes=class_filter or None,
        )
        person_detections = [
            item
            for item in detections
            if item["label"] in PERSON_LABELS
            and float(item["confidence"]) >= self.person_confidence_threshold
        ]
        phone_detections = [
            item
            for item in detections
            if item["label"] in PHONE_LABELS
            and float(item["confidence"]) >= self.phone_confidence_threshold
        ]
        visual = self.extract_visual_evidence(frame)
        phone_present = bool(phone_detections)
        phone_confidence = max((float(item["confidence"]) for item in phone_detections), default=0.0)
        person_confidence = max((float(item["confidence"]) for item in person_detections), default=0.0)
        visual_person_evidence = bool(visual.get("face_visible") or visual.get("pose_visible"))
        person_present = bool(person_detections or phone_present or visual_person_evidence)
        presence_focus_ready = (
            person_confidence >= self.presence_focus_confidence_threshold
            and not phone_present
            and not bool(visual.get("focus_ready"))
        )
        if presence_focus_ready:
            visual = {
                **visual,
                "source": f"{visual.get('source') or 'unknown'}+person_presence",
                "visual_evidence_score": max(
                    float(visual.get("visual_evidence_score") or 0.0),
                    min(0.65, person_confidence),
                ),
                "focus_ready": True,
            }

        label = "unknown"
        confidence = max(person_confidence, float(visual.get("visual_evidence_score") or 0.0))
        if not person_present:
            reason = "当前帧未检测到人，等待连续时序确认离开。"
            confidence = 0.0
        elif phone_present:
            label = "distracted"
            confidence = phone_confidence
            reason = "检测到手机，这是明确分心证据。"
        elif bool(visual.get("focus_ready")):
            label = "focused"
            confidence = float(visual.get("visual_evidence_score") or 0.0)
            if presence_focus_ready:
                reason = "检测到人在画面中且未检测到手机；脸部/姿态证据不足，按低置信视觉证据判为疑似专注。"
            else:
                reason = "人在画面中，未检测到手机，脸部或姿态证据稳定。"
        elif self.visual_evidence_available():
            reason = "检测到人在画面中，但脸部或姿态证据不足。"
        else:
            reason = "检测到人在画面中；脸部/姿态模块不可用，不能保守判定专注。"

        evidence_labels = self.evidence_labels(
            person_present=person_present,
            phone_present=phone_present,
            visual=visual,
        )
        return FocusRecognitionResult(
            label=label,
            label_text=LABEL_TEXT[label],
            confidence=round(max(0.0, min(1.0, confidence)), 4),
            person_present=person_present,
            phone_present=phone_present,
            phone_confidence=round(phone_confidence, 4),
            face_visible=visual.get("face_visible"),
            head_centered=visual.get("head_centered"),
            pose_visible=visual.get("pose_visible"),
            visual_evidence_score=round(float(visual.get("visual_evidence_score") or 0.0), 4),
            behavior_labels=[],
            evidence_labels=evidence_labels,
            reason=reason,
            debug={
                **self.debug,
                "raw_label": "",
                "behavior_labels": [],
                "evidence_labels": evidence_labels,
                "person_present": person_present,
                "phone_present": phone_present,
                "phone_confidence": round(phone_confidence, 4),
                "visual_evidence": visual,
                "coco_labels": [item["label"] for item in detections],
            },
        )

    @staticmethod
    def classify_behavior(detections: List[Dict[str, Any]]) -> tuple[str, float, str]:
        distracted = [item for item in detections if item["label"] in DISTRACTED_BEHAVIORS]
        focused = [item for item in detections if item["label"] in FOCUSED_BEHAVIORS]
        unknown = [item for item in detections if item["label"] in UNKNOWN_BEHAVIORS]
        if distracted:
            best = max(distracted, key=lambda item: item["confidence"])
            return "distracted", float(best["confidence"]), str(best["label"])
        if focused:
            best = max(focused, key=lambda item: item["confidence"])
            return "focused", float(best["confidence"]), str(best["label"])
        if unknown:
            best = max(unknown, key=lambda item: item["confidence"])
            return "unknown", float(best["confidence"]), str(best["label"])
        return "unknown", 0.0, ""

    def best_detection(self, results: Iterable[Any]) -> tuple[str, float]:
        detections = self.extract_detections(results, self._coco_model)
        if not detections:
            return "", 0.0
        best = max(detections, key=lambda item: item["confidence"])
        return str(best["label"]), float(best["confidence"])

    def _predict_model(
        self,
        model: Any,
        frame: Any,
        threshold: float,
        debug_key: str,
        *,
        classes: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        if model is None:
            return []
        try:
            kwargs: Dict[str, Any] = {"conf": threshold, "verbose": False}
            if classes:
                kwargs["classes"] = classes
            results = model.predict(frame, **kwargs)
            return self.extract_detections(results, model)
        except Exception as exc:
            self.debug[debug_key]["last_inference_error"] = str(exc)
            return []

    def extract_detections(self, results: Iterable[Any], model: Any) -> List[Dict[str, Any]]:
        detections: List[Dict[str, Any]] = []
        class_names = getattr(model, "names", {}) or {}
        for result in results or []:
            names = getattr(result, "names", {}) or class_names
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(self.scalar_value(getattr(box, "cls", [0])))
                confidence = float(self.scalar_value(getattr(box, "conf", [0.0])))
                raw_label = str(names.get(class_id, class_id))
                detections.append(
                    {
                        "class_id": class_id,
                        "label": self.normalize_raw_label(raw_label),
                        "confidence": confidence,
                    }
                )
        return detections

    def extract_visual_evidence(self, frame: Any) -> Dict[str, Any]:
        if self._evidence_extractor:
            try:
                return self.normalize_visual_evidence(self._evidence_extractor(frame))
            except Exception as exc:
                self.debug["visual_evidence_error"] = str(exc)
                return self.empty_visual_evidence("custom_error")
        if self._mp_face_mesh or self._mp_pose:
            return self.extract_mediapipe_evidence(frame)
        if self._opencv_face_cascade is not None:
            return self.extract_opencv_face_evidence(frame)
        return self.empty_visual_evidence("unavailable")

    def extract_mediapipe_evidence(self, frame: Any) -> Dict[str, Any]:
        try:
            image_rgb = self.frame_to_rgb(frame)
            face_result = self._mp_face_mesh.process(image_rgb) if self._mp_face_mesh else None
            pose_result = self._mp_pose.process(image_rgb) if self._mp_pose else None
            hand_result = self._mp_hands.process(image_rgb) if self._mp_hands else None
            face_visible = bool(getattr(face_result, "multi_face_landmarks", None))
            head_centered = False
            if face_visible:
                landmarks = face_result.multi_face_landmarks[0].landmark
                xs = [float(item.x) for item in landmarks]
                ys = [float(item.y) for item in landmarks]
                center_x = (min(xs) + max(xs)) / 2
                center_y = (min(ys) + max(ys)) / 2
                face_width = max(xs) - min(xs)
                head_centered = 0.15 <= center_x <= 0.85 and 0.05 <= center_y <= 0.9 and face_width >= 0.06
            pose_visible = False
            if getattr(pose_result, "pose_landmarks", None):
                landmarks = pose_result.pose_landmarks.landmark
                shoulder_ids = [11, 12]
                visible_shoulders = [
                    landmarks[index]
                    for index in shoulder_ids
                    if index < len(landmarks) and getattr(landmarks[index], "visibility", 0.0) >= 0.35
                ]
                pose_visible = len(visible_shoulders) >= 1
            hand_visible = bool(getattr(hand_result, "multi_hand_landmarks", None))
            score = 0.0
            if face_visible:
                score += 0.35
            if head_centered:
                score += 0.25
            if pose_visible:
                score += 0.2
            focus_ready = score >= self.visual_evidence_threshold and (
                (face_visible and head_centered) or pose_visible
            )
            return self.normalize_visual_evidence(
                {
                    "source": "mediapipe",
                    "face_visible": face_visible,
                    "head_centered": head_centered,
                    "pose_visible": pose_visible,
                    "hand_visible": hand_visible,
                    "visual_evidence_score": score,
                    "focus_ready": focus_ready,
                }
            )
        except Exception as exc:
            self.debug["mediapipe"]["last_inference_error"] = str(exc)
            return self.empty_visual_evidence("mediapipe_error")

    def extract_opencv_face_evidence(self, frame: Any) -> Dict[str, Any]:
        try:
            import cv2

            if frame is None or not hasattr(frame, "shape"):
                return self.empty_visual_evidence("opencv_no_frame")
            if len(frame.shape) == 3:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            else:
                gray = frame
            faces = self._opencv_face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(40, 40),
            )
            if len(faces) == 0:
                return self.normalize_visual_evidence({"source": "opencv_face"})
            height, width = gray.shape[:2]
            x, y, w, h = max(faces, key=lambda item: int(item[2]) * int(item[3]))
            center_x = (x + w / 2) / max(1, width)
            center_y = (y + h / 2) / max(1, height)
            face_ratio = w / max(1, width)
            head_centered = 0.15 <= center_x <= 0.85 and 0.05 <= center_y <= 0.9 and face_ratio >= 0.06
            score = 0.65 if head_centered else 0.4
            return self.normalize_visual_evidence(
                {
                    "source": "opencv_face",
                    "face_visible": True,
                    "head_centered": head_centered,
                    "pose_visible": None,
                    "visual_evidence_score": score,
                    "focus_ready": head_centered and score >= self.visual_evidence_threshold,
                }
            )
        except Exception as exc:
            self.debug["opencv_face"]["last_inference_error"] = str(exc)
            return self.empty_visual_evidence("opencv_face_error")

    def _load_models(self) -> None:
        if not self.debug["cv2_importable"]:
            self.debug["status"] = "cv2_missing"
            self.debug["message"] = "cv2 未安装，无法启用本地视觉识别。"
            return
        if not self.debug["ultralytics_importable"] and self._yolo_factory is None:
            self.debug["status"] = "ultralytics_missing"
            self.debug["message"] = "ultralytics 未安装，无法加载本地 YOLO 模型。"
            return
        self._coco_model = self._load_coco_model(self.person_weights_path, self._yolo_factory)
        self._person_model = self._coco_model
        self._model = self._coco_model
        self.debug["status"] = "available" if self.is_available() else self.debug["coco"].get("status", "unavailable")
        self.debug["message"] = self.status_message() if self.is_available() else "本地 YOLO COCO 权重文件不存在或不可用。"

    def _load_coco_model(self, path: Optional[Path], factory: Optional[Callable[[str], Any]]) -> Any:
        debug = self.debug["coco"]
        if path is None or not path.exists():
            debug["status"] = "weights_missing"
            return None
        try:
            if factory is None:
                configure_yolo_runtime_dir()
                from ultralytics import YOLO

                factory = YOLO
            model = factory(str(path))
            names = getattr(model, "names", {}) or {}
            normalized_names = {self.normalize_raw_label(value) for value in names.values()}
            if not normalized_names.intersection(PERSON_LABELS):
                debug["status"] = "unexpected_classes"
                debug["model_names"] = names
                return None
            self._person_class_ids = self.class_ids_for_labels(names, PERSON_LABELS)
            self._phone_class_ids = self.class_ids_for_labels(names, PHONE_LABELS)
            debug["model_names"] = names
            debug["person_class_ids"] = self._person_class_ids
            debug["phone_class_ids"] = self._phone_class_ids
            debug["model_loaded"] = True
            debug["status"] = "available"
            return model
        except Exception as exc:
            debug["status"] = "model_load_failed"
            debug["error"] = str(exc)
            return None

    def _load_visual_extractors(self) -> None:
        if self._evidence_extractor:
            self.debug["mediapipe"]["status"] = "custom_extractor"
            return
        if self._enable_mediapipe and self.debug["mediapipe"]["importable"]:
            self._load_mediapipe_extractors()
        if self._use_opencv_face_fallback and self._opencv_face_cascade is None:
            self._load_opencv_face_fallback()
        self.debug["message"] = self.status_message()

    def _load_mediapipe_extractors(self) -> None:
        try:
            import mediapipe as mp

            self._mp_face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,
                max_num_faces=1,
                refine_landmarks=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._mp_pose = mp.solutions.pose.Pose(
                static_image_mode=False,
                # MediaPipe wheels bundle the full pose model (complexity 1).
                # The lite model (complexity 0) is downloaded on first use,
                # which is unreliable in an offline packaged desktop app.
                model_complexity=1,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._mp_hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.debug["mediapipe"]["model_loaded"] = True
            self.debug["mediapipe"]["status"] = "available"
        except Exception as exc:
            self.debug["mediapipe"]["status"] = "load_failed"
            self.debug["mediapipe"]["error"] = str(exc)

    def _load_opencv_face_fallback(self) -> None:
        try:
            import cv2

            cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
            load_path = cascade_path
            if cascade_path.exists() and not self.is_ascii_path(cascade_path):
                temp_dir = Path(tempfile.gettempdir()) / "kaoyan_agent_cv2"
                temp_dir.mkdir(parents=True, exist_ok=True)
                ascii_path = temp_dir / "haarcascade_frontalface_default.xml"
                if not ascii_path.exists() or ascii_path.stat().st_size != cascade_path.stat().st_size:
                    shutil.copyfile(cascade_path, ascii_path)
                load_path = ascii_path
            cascade = cv2.CascadeClassifier(str(load_path))
            if cascade.empty():
                self.debug["opencv_face"]["status"] = "cascade_missing"
                return
            self._opencv_face_cascade = cascade
            self.debug["opencv_face"]["model_loaded"] = True
            self.debug["opencv_face"]["status"] = "available"
        except Exception as exc:
            self.debug["opencv_face"]["status"] = "load_failed"
            self.debug["opencv_face"]["error"] = str(exc)

    def _sync_legacy_debug_fields(self) -> None:
        behavior = self.debug["behavior"]
        self.debug.update(
            {
                "configured_weights_path": behavior["configured_weights_path"],
                "weights_found": behavior["weights_found"],
                "weight_candidates": behavior["weight_candidates"],
                "weights_path": self.debug["coco"]["weights_path"],
                "confidence_threshold": self.person_confidence_threshold,
                "model_loaded": self.debug["coco"]["model_loaded"],
                "model_names": self.debug["coco"]["model_names"],
                "last_inference_error": self.debug["coco"]["last_inference_error"],
            }
        )

    @staticmethod
    def evidence_labels(*, person_present: bool, phone_present: bool, visual: Dict[str, Any]) -> List[str]:
        labels: list[str] = []
        if person_present:
            labels.append("person")
        if phone_present:
            labels.append("cell_phone")
        for key in ("face_visible", "head_centered", "pose_visible"):
            if visual.get(key) is True:
                labels.append(key)
        return labels

    @staticmethod
    def class_ids_for_labels(names: Dict[Any, Any], labels: set[str]) -> List[int]:
        ids: list[int] = []
        for key, value in names.items():
            if LocalYoloFocusRecognizer.normalize_raw_label(value) in labels:
                try:
                    ids.append(int(key))
                except (TypeError, ValueError):
                    continue
        return ids

    @staticmethod
    def empty_visual_evidence(source: str) -> Dict[str, Any]:
        return {
            "source": source,
            "face_visible": None,
            "head_centered": None,
            "pose_visible": None,
            "hand_visible": None,
            "visual_evidence_score": 0.0,
            "focus_ready": False,
        }

    def normalize_visual_evidence(self, data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        payload = dict(data or {})
        face_visible = self.optional_bool(payload.get("face_visible"))
        head_centered = self.optional_bool(payload.get("head_centered"))
        pose_visible = self.optional_bool(payload.get("pose_visible"))
        hand_visible = self.optional_bool(payload.get("hand_visible"))
        score = max(0.0, min(1.0, float(payload.get("visual_evidence_score") or 0.0)))
        focus_ready = bool(payload.get("focus_ready")) or (
            score >= self.visual_evidence_threshold
            and ((face_visible is True and head_centered is True) or pose_visible is True)
        )
        return {
            "source": str(payload.get("source") or "unknown"),
            "face_visible": face_visible,
            "head_centered": head_centered,
            "pose_visible": pose_visible,
            "hand_visible": hand_visible,
            "visual_evidence_score": round(score, 4),
            "focus_ready": focus_ready,
        }

    @staticmethod
    def optional_bool(value: Any) -> Optional[bool]:
        if value is None:
            return None
        return bool(value)

    @staticmethod
    def is_ascii_path(path: Path) -> bool:
        try:
            str(path).encode("ascii")
            return True
        except UnicodeEncodeError:
            return False

    @staticmethod
    def frame_to_rgb(frame: Any) -> Any:
        try:
            import cv2

            return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception:
            return frame

    @staticmethod
    def scalar_value(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, (list, tuple)) and value:
            return LocalYoloFocusRecognizer.scalar_value(value[0])
        if hasattr(value, "item"):
            return float(value.item())
        if hasattr(value, "__getitem__"):
            try:
                return LocalYoloFocusRecognizer.scalar_value(value[0])
            except Exception:
                return 0.0
        return 0.0

    @staticmethod
    def normalize_raw_label(raw_label: Any) -> str:
        return str(raw_label or "").strip().lower().replace("-", "_").replace(" ", "_")

    @staticmethod
    def normalize_label(raw_label: str) -> str:
        value = LocalYoloFocusRecognizer.normalize_raw_label(raw_label)
        if value in FOCUSED_BEHAVIORS:
            return "focused"
        if value in DISTRACTED_BEHAVIORS:
            return "distracted"
        return "unknown"

    @staticmethod
    def file_sha256(path: Optional[Path]) -> str:
        if path is None or not path.exists():
            return ""
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
