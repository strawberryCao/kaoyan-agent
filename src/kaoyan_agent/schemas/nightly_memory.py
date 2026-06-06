from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


ProblemType = Literal[
    "knowledge_gap",
    "method_gap",
    "planning_issue",
    "execution_issue",
    "emotion_issue",
    "cognitive_bias",
    "project_design",
    "other",
]
ProblemStatus = Literal["open", "resolved", "ignored"]
MemoryType = Literal[
    "preference",
    "learning_status",
    "weakness",
    "mistake_pattern",
    "intervention_result",
    "project_state",
    "strategy",
]
MemoryOperation = Literal["insert", "update", "merge", "skip"]
ActionType = Literal[
    "study_task",
    "review_task",
    "project_task",
    "clarification",
    "follow_up",
]


class StrictNightlyModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class KeyEvent(StrictNightlyModel):
    event_type: str = Field(min_length=1)
    content: str = Field(min_length=1)
    importance: int = Field(ge=1, le=5)


class DiscoveredProblem(StrictNightlyModel):
    problem_type: ProblemType
    subject: str = ""
    description: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list, min_length=1)
    root_cause: str = ""
    severity: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0, le=1)
    value_score: int = Field(ge=1, le=5)
    suggested_action: str = ""
    status: ProblemStatus = "open"


class MemoryUpdate(StrictNightlyModel):
    operation: MemoryOperation
    memory_type: MemoryType
    content: str = ""
    importance: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0, le=1)
    merge_key: str = ""
    reason: str = ""


class NextAction(StrictNightlyModel):
    action_type: ActionType
    content: str = Field(min_length=1)
    related_problem: str = ""
    priority: int = Field(ge=1, le=5)


class NightlyMemoryUpdateOutput(StrictNightlyModel):
    daily_summary: str
    key_events: list[KeyEvent] = Field(default_factory=list)
    discovered_problems: list[DiscoveredProblem] = Field(default_factory=list)
    memory_updates: list[MemoryUpdate] = Field(default_factory=list)
    next_actions: list[NextAction] = Field(default_factory=list)

