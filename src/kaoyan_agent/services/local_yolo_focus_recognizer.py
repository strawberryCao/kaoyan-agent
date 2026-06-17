from __future__ import annotations

import importlib.util
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from kaoyan_agent.core.paths import PROJECT_ROOT


LABEL_TEXT = {
    "focused": "专注",
    "distracted": "分心",
    "away": "离开",
    "unknown": "无法判断",
}

LABEL_MAP = {
    "focused": "focused",
    "focus": "focused",
    "study": "focused",
    "studying": "focused",
    "reading": "focused",
    "writing": "focused",
    "book": "focused",
    "person": "focused",
    "phone": "distracted",
    "using_phone": "distracted",
    "distracted": "distracted",
    "looking_away": "distracted",
    "sleep": "distracted",
    "empty": "away",
    "away": "away",
    "no_person": "away",
    "none": "away",
}

SCAN_DIRS = ("models", "weights", "runs", "src")


@dataclass
class FocusRecognitionResult:
    label: str = "unknown"
    label_text: str = "无法判断"
    confidence: float = 0.0
    debug: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def find_yolo_weight_candidates(
    configured_path: Optional[Path | str] = None,
    project_root: Optional[Path] = None,
) -> List[Path]:
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


def resolve_candidate_path(value: Path | str, project_root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project_root / path


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
    """Local YOLO frame recognizer used by the supervision page."""

    def __init__(
        self,
        weights_path: Optional[Path | str],
        confidence_threshold: float = 0.5,
        *,
        project_root: Optional[Path] = None,
        camera_id: int = 0,
        yolo_factory: Optional[Callable[[str], Any]] = None,
        check_camera: bool = False,
    ):
        self.project_root = Path(project_root or PROJECT_ROOT)
        self.configured_weights_path = Path(weights_path) if weights_path else None
        self.confidence_threshold = max(0.0, min(1.0, confidence_threshold))
        self.camera_id = int(camera_id)
        self._model = None
        self._available = False
        self._yolo_factory = yolo_factory
        self.weight_candidates = find_yolo_weight_candidates(
            self.configured_weights_path,
            self.project_root,
        )
        self.weights_path = self.resolve_weights_path()
        self.debug: Dict[str, Any] = {
            "configured_weights_path": str(self.configured_weights_path or ""),
            "weights_found": bool(self.weight_candidates),
            "weight_candidates": [str(path) for path in self.weight_candidates],
            "weights_path": str(self.weights_path or ""),
            "confidence_threshold": self.confidence_threshold,
            "camera_id": self.camera_id,
            "cv2_importable": module_available("cv2"),
            "ultralytics_importable": module_available("ultralytics"),
            "streamlit_webrtc_importable": module_available("streamlit_webrtc"),
            "model_loaded": False,
            "model_names": {},
            "last_inference_error": "",
        }
        if check_camera:
            self.debug["camera"] = diagnose_camera_access(self.camera_id)
        self._load_model()

    def is_available(self) -> bool:
        return self._available

    def status_message(self) -> str:
        return str(self.debug.get("message") or self.debug.get("error") or "")

    def resolve_weights_path(self) -> Optional[Path]:
        if self.configured_weights_path:
            return resolve_candidate_path(self.configured_weights_path, self.project_root)
        for candidate in self.weight_candidates:
            if candidate.exists():
                return candidate
        return None

    def predict_frame(self, frame) -> FocusRecognitionResult:
        if not self.is_available() or self._model is None:
            return FocusRecognitionResult(
                label="unknown",
                label_text=LABEL_TEXT["unknown"],
                confidence=0.0,
                debug={**self.debug, "status": "unavailable"},
            )
        try:
            results = self._model.predict(
                frame,
                conf=self.confidence_threshold,
                verbose=False,
            )
        except Exception as exc:
            self.debug["status"] = "predict_failed"
            self.debug["last_inference_error"] = str(exc)
            return FocusRecognitionResult(
                label="unknown",
                label_text=LABEL_TEXT["unknown"],
                confidence=0.0,
                debug={**self.debug, "error": str(exc)},
            )

        best_label, best_confidence = self.best_detection(results)
        model_names = getattr(self._model, "names", {}) or {}
        if not best_label:
            return FocusRecognitionResult(
                label="away",
                label_text=LABEL_TEXT["away"],
                confidence=1.0,
                debug={**self.debug, "model_names": model_names, "raw_label": ""},
            )

        normalized = self.normalize_label(best_label)
        return FocusRecognitionResult(
            label=normalized,
            label_text=LABEL_TEXT.get(normalized, LABEL_TEXT["unknown"]),
            confidence=round(best_confidence, 4),
            debug={
                **self.debug,
                "model_names": model_names,
                "raw_label": best_label,
            },
        )

    def best_detection(self, results: Iterable[Any]) -> tuple[str, float]:
        best_label = ""
        best_confidence = 0.0
        class_names = getattr(self._model, "names", {}) or {}
        for result in results or []:
            names = getattr(result, "names", {}) or class_names
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                class_id = self.scalar_value(getattr(box, "cls", [0]))
                confidence = float(self.scalar_value(getattr(box, "conf", [0.0])))
                if confidence >= best_confidence:
                    best_confidence = confidence
                    best_label = str(names.get(int(class_id), int(class_id)))
        return best_label, best_confidence

    def _load_model(self) -> None:
        if self.weights_path is None:
            self.debug["status"] = "weights_not_found"
            self.debug["message"] = "未找到 .pt 权重文件，请放到 models/、weights/、runs/、src/ 或项目根目录。"
            return
        if not self.weights_path.exists():
            self.debug["status"] = "weights_missing"
            self.debug["message"] = f"本地 YOLO 权重文件不存在：{self.weights_path}"
            return
        if not self.debug["cv2_importable"]:
            self.debug["status"] = "cv2_missing"
            self.debug["message"] = "cv2 未安装，无法启用本地视觉识别。"
            return
        if not self.debug["ultralytics_importable"] and self._yolo_factory is None:
            self.debug["status"] = "ultralytics_missing"
            self.debug["message"] = "ultralytics 未安装，无法加载本地 YOLO 模型。"
            return
        try:
            yolo_factory = self._yolo_factory
            if yolo_factory is None:
                from ultralytics import YOLO

                yolo_factory = YOLO
            self._model = yolo_factory(str(self.weights_path))
            self.debug["model_names"] = getattr(self._model, "names", {}) or {}
            self.debug["model_loaded"] = True
            self.debug["status"] = "available"
            self.debug["message"] = "本地 YOLO 模型已加载。"
            self._available = True
        except Exception as exc:
            self.debug["status"] = "model_load_failed"
            self.debug["message"] = f"本地 YOLO 模型加载失败：{exc}"
            self.debug["error"] = str(exc)

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
    def normalize_label(raw_label: str) -> str:
        value = raw_label.strip().lower().replace("-", "_").replace(" ", "_")
        return LABEL_MAP.get(value, "unknown")
