from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


FocusStateType = Literal["focused", "away", "distracted", "blocked", "unknown"]


class FocusStateRecognitionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    state_type: FocusStateType
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=1)


class FocusReportOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    effective_focus_minutes: int = Field(ge=0)
    away_count: int = Field(ge=0)
    distracted_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    longest_focus_minutes: int = Field(ge=0)
    focus_quality: str = Field(min_length=1)
    ai_summary: str = Field(min_length=1)
    possible_problem_signal: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)


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
