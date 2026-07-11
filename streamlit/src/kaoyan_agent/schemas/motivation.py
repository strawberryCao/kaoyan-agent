from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


SignLevel = Literal["top", "good", "steady", "small", "calm"]


class DailySignOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sign_level: SignLevel
    sign_text: str = Field(min_length=1)
    today_advice: str = Field(min_length=1)
    action: str = Field(min_length=1)


class RandomTaskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    estimated_minutes: int = Field(ge=1, le=20)
    reason: str = Field(min_length=1)


class SoothingTaskOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    estimated_minutes: int = Field(ge=1, le=10)
    reason: str = Field(min_length=1)
