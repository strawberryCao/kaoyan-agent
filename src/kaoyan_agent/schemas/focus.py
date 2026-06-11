from typing import Literal

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
