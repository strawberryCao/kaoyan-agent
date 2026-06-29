from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MistakeReason = Literal[
    "concept_gap",
    "method_gap",
    "calculation_error",
    "careless_error",
    "memory_gap",
    "expression_gap",
    "unknown",
]


class PracticeReviewCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_points: str | list[str] = Field(min_length=1)
    mistake_reason: MistakeReason
    analysis: str = Field(min_length=1)
    review_priority: int = Field(ge=1, le=5)
