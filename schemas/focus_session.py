from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FocusTimerStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    FINISHED = "finished"


class FocusSessionCreate(BaseModel):
    task_id: Optional[int] = None
    task_title: str
    subject: str = ""
    planned_minutes: int = Field(ge=1, le=480)


class FocusSessionFinish(BaseModel):
    actual_seconds: int = Field(ge=0)
    pause_count: int = Field(ge=0, default=0)
    completed: bool = False
    reflection: str = ""


class FocusSessionRecord(BaseModel):
    id: int
    task_id: Optional[int]
    task_title: str
    subject: str
    planned_minutes: int
    actual_seconds: int
    pause_count: int
    started_at: str
    ended_at: Optional[str]
    completed: bool
    reflection: str
    created_at: str

    @property
    def actual_minutes(self) -> float:
        return round(self.actual_seconds / 60, 1)


class FocusStats(BaseModel):
    today_sessions: int = 0
    today_focus_minutes: float = 0.0
    today_completed: int = 0
    week_sessions: int = 0
    week_focus_minutes: float = 0.0
    week_completed: int = 0
    total_sessions: int = 0
    total_focus_minutes: float = 0.0
    completion_rate: float = 0.0
    daily_minutes: dict[str, float] = Field(default_factory=dict)


class FocusTimerState(BaseModel):
    task_id: Optional[int] = None
    task_title: str = ""
    subject: str = ""
    planned_minutes: int = 25
    status: FocusTimerStatus = FocusTimerStatus.IDLE
    session_started_at: Optional[str] = None
    segment_started_at: Optional[str] = None
    accumulated_seconds: int = 0
    pause_count: int = 0
