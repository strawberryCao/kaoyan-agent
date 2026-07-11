from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DailyTaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class DailyTaskCreate(BaseModel):
    subject: str = ""
    task: str = Field(min_length=1)
    reason: str = ""
    estimated_minutes: int = Field(default=25, ge=1, le=480)
    related_problem_id: Optional[int] = None


class DailyTaskRecord(BaseModel):
    id: int
    subject: str = ""
    task: str
    reason: str = ""
    estimated_minutes: int
    related_problem_id: Optional[int] = None
    status: DailyTaskStatus
    created_at: str
    updated_at: str

    @property
    def display_title(self) -> str:
        if self.subject:
            return f"{self.subject} - {self.task}"
        return self.task
