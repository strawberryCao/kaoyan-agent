"""Evaluate the local focus detector on non-committed labeled video clips.

Manifest format:
[
  {"path": "D:/clips/reading.mp4", "expected_state": "focused"},
  {"path": "D:/clips/leave.mp4", "expected_state": "away", "transition_at": 4.2}
]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kaoyan_agent.core.settings import get_settings
from kaoyan_agent.services.focus_temporal_tracker import FocusTemporalTracker
from kaoyan_agent.services.local_yolo_focus_recognizer import (
    LocalYoloFocusRecognizer,
    find_yolo_weight_candidates,
)


ALLOWED_STATES = {"focused", "distracted", "away", "unknown"}


def evaluate_manifest(manifest_path: Path) -> dict[str, Any]:
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError("opencv-python is required for video evaluation") from exc

    settings = get_settings()
    candidates = find_yolo_weight_candidates(settings.yolo_focus_weights_path)
    recognizer = LocalYoloFocusRecognizer(
        candidates[0] if candidates else settings.yolo_focus_weights_path,
        confidence_threshold=settings.yolo_focus_confidence_threshold,
        person_weights_path=settings.yolo_person_weights_path,
        person_confidence_threshold=settings.yolo_person_confidence_threshold,
        phone_confidence_threshold=settings.focus_phone_confidence_threshold,
        visual_evidence_threshold=settings.focus_visual_evidence_threshold,
        presence_focus_confidence_threshold=settings.focus_presence_focus_confidence_threshold,
    )
    if not recognizer.is_fully_available():
        raise RuntimeError(recognizer.status_message())

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    clips: list[dict[str, Any]] = []
    sample_interval = 1.0 / max(1, settings.yolo_focus_inference_fps)

    for item in manifest:
        path = Path(str(item["path"]))
        expected = str(item["expected_state"])
        if expected not in ALLOWED_STATES:
            raise ValueError(f"Unsupported expected_state: {expected}")
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            raise FileNotFoundError(f"Cannot open video: {path}")
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        frame_step = max(1, round(fps * sample_interval))
        tracker = FocusTemporalTracker(
            away_confirm_seconds=settings.yolo_away_confirm_seconds,
            behavior_window_seconds=settings.yolo_behavior_window_seconds,
        )
        predictions: list[str] = []
        first_expected_at = None
        frame_index = 0
        try:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame_index % frame_step:
                    frame_index += 1
                    continue
                timestamp = frame_index / fps
                recognition = recognizer.predict_frame(frame)
                state = tracker.observe(recognition, timestamp).observation.state_type
                predictions.append(state)
                confusion[expected][state] += 1
                if state == expected and first_expected_at is None:
                    first_expected_at = timestamp
                frame_index += 1
        finally:
            capture.release()

        transition_at = item.get("transition_at")
        latency = None
        if transition_at is not None and first_expected_at is not None:
            latency = round(max(0.0, first_expected_at - float(transition_at)), 3)
        clips.append(
            {
                "path": str(path),
                "expected_state": expected,
                "samples": len(predictions),
                "prediction_counts": dict(Counter(predictions)),
                "first_expected_at": first_expected_at,
                "transition_latency_seconds": latency,
            }
        )

    total = sum(sum(row.values()) for row in confusion.values())
    correct = sum(confusion[state][state] for state in ALLOWED_STATES)
    return {
        "detector_version": "dual_yolo_v2",
        "accuracy": round(correct / total, 4) if total else 0.0,
        "confusion_matrix": {state: dict(counts) for state, counts in confusion.items()},
        "clips": clips,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_manifest(args.manifest)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
