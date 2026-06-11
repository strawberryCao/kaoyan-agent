from io import BytesIO
import os
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image

from kaoyan_agent.core.paths import DATA_DIR
from kaoyan_agent.vision.focus_state_rules import FocusRuleResult, FocusStateRuleEngine


class LocalYoloFocusDetector:
    """Run a trained YOLO model and convert detections to focus states."""

    def __init__(
        self,
        model_path: Path,
        confidence: float = 0.35,
        rule_engine: FocusStateRuleEngine | None = None,
    ):
        if not model_path.exists():
            raise FileNotFoundError(f"Local focus model not found: {model_path}")
        self.model_path = model_path
        self.confidence = confidence
        self.rule_engine = rule_engine or FocusStateRuleEngine()
        self._model = None

    def recognize(self, image_bytes: bytes) -> Dict[str, Any]:
        detections = self.detect(image_bytes)
        result = self.rule_engine.classify(detections)
        return self.to_recognition(result)

    def detect(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        yolo_config_dir = DATA_DIR / "ultralytics"
        yolo_config_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(yolo_config_dir.resolve()))
        try:
            from ultralytics import YOLO
        except ModuleNotFoundError as exc:
            raise RuntimeError("ultralytics is not installed.") from exc

        if self._model is None:
            self._model = YOLO(str(self.model_path))

        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        results = self._model.predict(image, conf=self.confidence, verbose=False)
        detections: List[Dict[str, Any]] = []
        for result in results:
            names = getattr(result, "names", {}) or {}
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                class_id = int(box.cls[0].item())
                confidence = float(box.conf[0].item())
                xyxy = [float(value) for value in box.xyxy[0].tolist()]
                detections.append(
                    {
                        "label": str(names.get(class_id, class_id)),
                        "confidence": confidence,
                        "box": xyxy,
                    }
                )
        return detections

    def to_recognition(self, result: FocusRuleResult) -> Dict[str, Any]:
        return {
            "state_type": result.state_type,
            "confidence": result.confidence,
            "explanation": result.explanation,
            "recognition_source": "local_yolo",
            "metrics": result.metrics,
        }
