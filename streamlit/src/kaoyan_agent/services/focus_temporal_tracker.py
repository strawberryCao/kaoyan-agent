from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Deque, Optional

from kaoyan_agent.schemas.focus import FocusStableObservationOutput


DETECTOR_VERSION = "zero_label_evidence_v1"


@dataclass(frozen=True)
class FocusStateSegment:
    state_type: str
    confidence: float
    explanation: str
    observed_seconds: int
    detector_version: str = DETECTOR_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TemporalFocusResult:
    observation: FocusStableObservationOutput
    completed_segment: Optional[FocusStateSegment] = None


class FocusTemporalTracker:
    """Convert noisy frame observations into stable, duration-bearing states."""

    def __init__(
        self,
        *,
        away_confirm_seconds: int = 10,
        behavior_window_seconds: int = 3,
        presence_grace_seconds: int = 2,
        heartbeat_seconds: int = 10,
    ):
        self.away_confirm_seconds = max(3, int(away_confirm_seconds))
        self.behavior_window_seconds = max(1, int(behavior_window_seconds))
        self.presence_grace_seconds = max(0, min(int(presence_grace_seconds), self.away_confirm_seconds))
        self.heartbeat_seconds = max(1, int(heartbeat_seconds))
        self._history: Deque[tuple[float, str, float]] = deque()
        self._monitoring_started_at: Optional[float] = None
        self._absence_started_at: Optional[float] = None
        self._state_started_at: Optional[float] = None
        self._segment_started_at: Optional[float] = None
        self._stable_state = "unknown"
        self._stable_confidence = 0.0
        self._stable_explanation = "等待稳定视觉证据。"
        self._last_person_present: Optional[bool] = None

    def observe(self, frame_result: Any, now: float) -> TemporalFocusResult:
        now = float(now)
        if self._monitoring_started_at is None:
            self._monitoring_started_at = now
            self._state_started_at = now
            self._segment_started_at = now

        person_present = getattr(frame_result, "person_present", None)
        raw_state = str(getattr(frame_result, "label", "unknown") or "unknown")
        confidence = float(getattr(frame_result, "confidence", 0.0) or 0.0)
        reason = str(getattr(frame_result, "reason", "") or "视觉证据不足。")
        phone_present = getattr(frame_result, "phone_present", None)
        face_visible = getattr(frame_result, "face_visible", None)
        head_centered = getattr(frame_result, "head_centered", None)
        pose_visible = getattr(frame_result, "pose_visible", None)
        visual_evidence_score = float(getattr(frame_result, "visual_evidence_score", 0.0) or 0.0)

        candidate, candidate_confidence, explanation, absence_seconds = self._candidate_state(
            now=now,
            person_present=person_present,
            raw_state=raw_state,
            confidence=confidence,
            reason=reason,
        )
        completed = None
        if candidate != self._stable_state:
            completed = self._complete_segment(now)
            self._stable_state = candidate
            self._stable_confidence = candidate_confidence
            self._stable_explanation = explanation
            self._state_started_at = now
            self._segment_started_at = now
        else:
            self._stable_confidence = candidate_confidence
            self._stable_explanation = explanation
            if self._segment_started_at is not None and now - self._segment_started_at >= self.heartbeat_seconds:
                completed = self._complete_segment(now)
                self._segment_started_at = now

        self._last_person_present = person_present
        observation = FocusStableObservationOutput.model_validate(
            {
                "state_type": self._stable_state,
                "confidence": max(0.0, min(1.0, self._stable_confidence)),
                "focus_score": self.focus_score(self._stable_state, self._stable_confidence),
                "explanation": self._stable_explanation,
                "state_elapsed_seconds": max(0, round(now - (self._state_started_at or now))),
                "monitoring_seconds": max(0, round(now - (self._monitoring_started_at or now))),
                "absence_seconds": max(0, round(absence_seconds)),
                "person_present": person_present,
                "phone_present": phone_present,
                "face_visible": face_visible,
                "head_centered": head_centered,
                "pose_visible": pose_visible,
                "visual_evidence_score": max(0.0, min(1.0, visual_evidence_score)),
                "detector_version": DETECTOR_VERSION,
            }
        )
        return TemporalFocusResult(observation=observation, completed_segment=completed)

    def flush(self, now: float) -> Optional[FocusStateSegment]:
        if self._monitoring_started_at is None:
            return None
        segment = self._complete_segment(float(now))
        self._segment_started_at = float(now)
        return segment

    def _candidate_state(
        self,
        *,
        now: float,
        person_present: Optional[bool],
        raw_state: str,
        confidence: float,
        reason: str,
    ) -> tuple[str, float, str, float]:
        absence_seconds = 0.0
        if person_present is False:
            if self._last_person_present is not False or self._absence_started_at is None:
                self._absence_started_at = now
                self._history.clear()
            absence_seconds = max(0.0, now - self._absence_started_at)
            if absence_seconds < self.presence_grace_seconds and self._stable_state in {"focused", "distracted"}:
                return self._stable_state, self._stable_confidence, "人体检测短暂丢失，保持上一稳定状态。", absence_seconds
            if absence_seconds < self.away_confirm_seconds:
                return "unknown", 0.0, f"离开确认中（{round(absence_seconds)}/{self.away_confirm_seconds} 秒）。", absence_seconds
            return "away", 1.0, f"连续 {self.away_confirm_seconds} 秒未检测到人。", absence_seconds

        self._absence_started_at = None
        cutoff = now - self.behavior_window_seconds
        self._history.append((now, raw_state, confidence))
        while self._history and self._history[0][0] < cutoff:
            self._history.popleft()

        distracted = [item for item in self._history if item[1] == "distracted"]
        focused = [item for item in self._history if item[1] == "focused"]
        if len(distracted) >= 2:
            return "distracted", max(item[2] for item in distracted), "连续检测到手机等明确分心证据。", 0.0
        if len(focused) >= 2 and len(focused) >= len(self._history) / 2:
            return "focused", max(item[2] for item in focused), "最近视觉证据稳定：人在画面中、未检测到手机、脸部或姿态证据可用。", 0.0
        if person_present is True:
            return "unknown", confidence, "检测到人在画面中，但脸部或姿态证据不足。", 0.0
        return "unknown", confidence, reason, 0.0

    def _complete_segment(self, now: float) -> Optional[FocusStateSegment]:
        if self._segment_started_at is None:
            return None
        duration = max(0, round(now - self._segment_started_at))
        if duration <= 0:
            return None
        return FocusStateSegment(
            state_type=self._stable_state,
            confidence=max(0.0, min(1.0, self._stable_confidence)),
            explanation=self._stable_explanation,
            observed_seconds=duration,
        )

    @staticmethod
    def focus_score(state_type: str, confidence: float) -> int:
        confidence = max(0.0, min(1.0, float(confidence)))
        if state_type == "focused":
            return round(confidence * 100)
        if state_type == "distracted":
            return max(0, round((1.0 - confidence) * 40))
        if state_type in {"away", "blocked"}:
            return 0
        return 0
