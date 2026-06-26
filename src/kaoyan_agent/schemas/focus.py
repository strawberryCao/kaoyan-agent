from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


FocusStateType = Literal["focused", "away", "distracted", "blocked", "unknown"]
FocusEvidenceStatus = Literal["sufficient", "insufficient", "legacy_unverified"]


class FocusStateRecognitionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_type: FocusStateType
    confidence: float = Field(ge=0.0, le=1.0)
    focus_score: int = Field(default=0, ge=0, le=100)
    explanation: str = Field(min_length=1)


class FocusStableObservationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_type: FocusStateType
    confidence: float = Field(ge=0.0, le=1.0)
    focus_score: int = Field(ge=0, le=100)
    explanation: str = Field(min_length=1)
    state_elapsed_seconds: int = Field(default=0, ge=0)
    monitoring_seconds: int = Field(default=0, ge=0)
    absence_seconds: int = Field(default=0, ge=0)
    person_present: Optional[bool] = None
    phone_present: Optional[bool] = None
    face_visible: Optional[bool] = None
    head_centered: Optional[bool] = None
    pose_visible: Optional[bool] = None
    visual_evidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    detector_version: str = Field(default="zero_label_evidence_v1", min_length=1)


class FocusReportNarrativeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_summary: str = Field(min_length=1)
    possible_problem_signal: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)


class FocusReportOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus_score: int = Field(default=0, ge=0, le=100)
    effective_focus_minutes: int = Field(ge=0)
    away_count: int = Field(ge=0)
    distracted_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    longest_focus_minutes: int = Field(ge=0)
    focus_quality: str = Field(min_length=1)
    ai_summary: str = Field(min_length=1)
    possible_problem_signal: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)
    monitored_seconds: int = Field(default=0, ge=0)
    coverage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    classified_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    focused_seconds: int = Field(default=0, ge=0)
    distracted_seconds: int = Field(default=0, ge=0)
    away_seconds: int = Field(default=0, ge=0)
    unknown_seconds: int = Field(default=0, ge=0)
    evidence_status: FocusEvidenceStatus = "insufficient"
    detector_version: str = Field(default="zero_label_evidence_v1", min_length=1)


class FocusTimerStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"


class FocusTimerState(BaseModel):
    task_id: Optional[int] = None
    task_title: str = ""
    subject: str = ""
    planned_minutes: int = Field(default=25, ge=1, le=480)
    status: FocusTimerStatus = FocusTimerStatus.IDLE
    session_started_at: Optional[str] = None
    segment_started_at: Optional[str] = None
    accumulated_seconds: int = Field(default=0, ge=0)
    pause_count: int = Field(default=0, ge=0)
