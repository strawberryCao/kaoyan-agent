from collections import Counter
from typing import Any, Dict, List, Optional

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.schemas.focus import (
    FocusReportOutput,
    FocusStateRecognitionOutput,
)
from kaoyan_agent.services.llm_client import (
    run_structured_agent,
    run_structured_vision_agent,
    supports_vision_model,
)
from kaoyan_agent.vision.yolo_focus_detector import LocalYoloFocusDetector


ALLOWED_STATES = {"focused", "away", "distracted", "blocked", "unknown"}

VISION_SYSTEM_PROMPT = """
You are a privacy-aware study supervision classifier.
Classify only visible study state from the camera snapshot.
Do not identify the person, infer sensitive attributes, or store image content.
Allowed state_type values: focused, away, distracted, blocked, unknown.
Return structured output only.
""".strip()

REPORT_SYSTEM_PROMPT = """
You are a study supervision analyst for a Chinese postgraduate exam preparation agent.
Turn focus session metrics and camera state events into a short report that can
become problem-discovery evidence. Prefer concrete signals over moral judgment.
Return structured output only.
""".strip()


class FocusSupervisionAgent:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._local_detector: Optional[LocalYoloFocusDetector] = None

    def recognize_snapshot(
        self,
        image_bytes: bytes,
        mime_type: str = "image/png",
        context: str = "",
    ) -> Dict[str, Any]:
        fallback = {
            "state_type": "unknown",
            "confidence": 0.0,
            "explanation": "当前视觉识别不可用，已切换为手动状态记录。",
            "recognition_source": "manual_fallback",
        }
        local_result = self.recognize_with_local_model(image_bytes)
        if local_result:
            return self.normalize_recognition(local_result, fallback)

        if not supports_vision_model(self.settings):
            result = self.normalize_recognition(fallback, fallback)
            result["generation_error"] = (
                f"Vision is disabled for model {self.settings.llm_model}."
            )
            return result

        prompt = (
            "Classify this camera snapshot for a study supervision session. "
            "Use one of: focused, away, distracted, blocked, unknown. "
            f"Optional user context: {context or 'none'}"
        )
        try:
            output = run_structured_vision_agent(
                FocusStateRecognitionOutput,
                prompt,
                image_bytes,
                mime_type,
                system_prompt=VISION_SYSTEM_PROMPT,
                settings=self.settings,
                temperature=0.0,
            )
            return self.normalize_recognition(output.model_dump(), fallback)
        except Exception as exc:
            result = self.normalize_recognition(fallback, fallback)
            result["generation_error"] = str(exc)
            return result

    def recognize_with_local_model(self, image_bytes: bytes) -> Optional[Dict[str, Any]]:
        model_path = getattr(self.settings, "focus_local_model_path", None)
        if not model_path:
            return None
        try:
            if self._local_detector is None:
                self._local_detector = LocalYoloFocusDetector(
                    model_path=model_path,
                    confidence=getattr(self.settings, "focus_local_model_confidence", 0.35),
                )
            return self._local_detector.recognize(image_bytes)
        except Exception:
            self._local_detector = None
            return None

    def generate_report(
        self,
        session: Dict[str, Any],
        state_events: List[Dict[str, Any]],
        timeline_events: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        fallback = self.build_fallback_report(session, state_events)
        prompt = self.build_report_prompt(session, state_events, timeline_events or [])
        try:
            output = run_structured_agent(
                FocusReportOutput,
                prompt,
                system_prompt=REPORT_SYSTEM_PROMPT,
                settings=self.settings,
                temperature=0.2,
            )
            return self.normalize_report(output.model_dump(), fallback)
        except Exception as exc:
            result = self.normalize_report(fallback, fallback)
            result["generation_error"] = str(exc)
            return result

    def normalize_recognition(
        self,
        recognition: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        state_type = str(recognition.get("state_type") or "").strip()
        if state_type not in ALLOWED_STATES:
            state_type = fallback["state_type"]
        normalized = {
            "state_type": state_type,
            "confidence": self.clamp_float(
                recognition.get("confidence"),
                float(fallback.get("confidence", 0.0)),
                0.0,
                1.0,
            ),
            "explanation": str(
                recognition.get("explanation") or fallback["explanation"]
            ).strip(),
        }
        if recognition.get("recognition_source"):
            normalized["recognition_source"] = str(recognition["recognition_source"])
        if recognition.get("metrics") is not None:
            normalized["metrics"] = recognition["metrics"]
        return normalized

    def build_report_prompt(
        self,
        session: Dict[str, Any],
        state_events: List[Dict[str, Any]],
        timeline_events: List[Dict[str, Any]],
    ) -> str:
        return (
            "Generate one focus supervision report from this session.\n"
            f"Session: {session}\n"
            f"State events: {state_events}\n"
            f"Timeline events: {timeline_events}\n"
            "Connect patterns to possible learning problems, for example startup "
            "difficulty, oversized plan, unclear next action, or execution drift."
        )

    def build_fallback_report(
        self,
        session: Dict[str, Any],
        state_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        planned = self.safe_int(session.get("planned_minutes"), 0)
        actual = self.safe_int(session.get("actual_minutes"), planned)
        counts = Counter(str(event.get("state_type") or "unknown") for event in state_events)
        total = sum(counts.values())
        focused = counts.get("focused", 0)
        away = counts.get("away", 0)
        distracted = counts.get("distracted", 0)
        blocked = counts.get("blocked", 0)
        effective = actual if total == 0 else round(actual * focused / total)

        if total == 0:
            quality = "no camera evidence"
        elif focused / total >= 0.75:
            quality = "stable"
        elif away + distracted + blocked >= focused:
            quality = "unstable"
        else:
            quality = "mixed"

        possible_signal = "No strong problem signal yet."
        if total == 0:
            possible_signal = "Focus session lacks supervision evidence."
        elif away > 0 and away >= focused:
            possible_signal = "User may leave soon after starting; possible startup or environment issue."
        elif distracted > 0 and distracted >= focused:
            possible_signal = "Frequent distraction may indicate task pressure or unclear next action."
        elif actual < planned:
            possible_signal = "Actual focus time was lower than planned; task size may be too large."

        return {
            "effective_focus_minutes": max(0, effective),
            "away_count": away,
            "distracted_count": distracted,
            "blocked_count": blocked,
            "longest_focus_minutes": max(0, effective),
            "focus_quality": quality,
            "ai_summary": (
                f"Recorded {total} supervision states: "
                f"{focused} focused, {away} away, {distracted} distracted, {blocked} blocked."
            ),
            "possible_problem_signal": possible_signal,
            "suggested_action": "Review this focus session in the nightly memory update.",
        }

    def normalize_report(
        self,
        report: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "effective_focus_minutes": self.safe_int(
                report.get("effective_focus_minutes"),
                fallback["effective_focus_minutes"],
            ),
            "away_count": self.safe_int(report.get("away_count"), fallback["away_count"]),
            "distracted_count": self.safe_int(
                report.get("distracted_count"),
                fallback["distracted_count"],
            ),
            "blocked_count": self.safe_int(
                report.get("blocked_count"),
                fallback["blocked_count"],
            ),
            "longest_focus_minutes": self.safe_int(
                report.get("longest_focus_minutes"),
                fallback["longest_focus_minutes"],
            ),
            "focus_quality": str(
                report.get("focus_quality") or fallback["focus_quality"]
            ).strip(),
            "ai_summary": str(report.get("ai_summary") or fallback["ai_summary"]).strip(),
            "possible_problem_signal": str(
                report.get("possible_problem_signal")
                or fallback["possible_problem_signal"]
            ).strip(),
            "suggested_action": str(
                report.get("suggested_action") or fallback["suggested_action"]
            ).strip(),
        }

    def safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return max(0, default)

    def clamp_float(
        self,
        value: Any,
        default: float,
        minimum: float,
        maximum: float,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(minimum, min(maximum, number))
