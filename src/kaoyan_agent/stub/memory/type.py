from typing import Literal, TypedDict

Message = tuple[Literal["user", "assistant"], str]

MemoryType = Literal[
    "user_profile",
    "preference",
    "learning_state",
    "weakness",
    "project_state",
    "strategy",
]


MemoryStatus = Literal[
    "active",
    "archived",
    "conflict",
    "pending_confirm",
]

ProblemStatus = Literal[
    "open",
    "resolved",
    "ignored",
]


Action = Literal[
    "study_task",
    "review_task",
    "project_task",
    "clarification",
    "follow_up",
]


Emotion = Literal[
    "positive",
    "neutral",
    "anxious",
    "frustrated",
    "exhausted",
    "hopeful",
    "discouraged",
    "confident",
    "overwhelmed",
]


class Memory(TypedDict):
    uuid: str
    type: MemoryType
    content: str
    confidence_score: int
    effectiveness_score: int
    add_at: str
    updated_at: str
    last_used_at: str
    status: MemoryStatus


class Problem(TypedDict):
    uuid: str
    title: str
    description: str
    impact_score: int
    add_at: str
    status: ProblemStatus


class Summary(TypedDict):
    summary: str
    next_action: Action
    emotion: Emotion
    stress_level: int


class Diary(TypedDict):
    add_at: str
    summary: Summary
    new_memories: list[Memory]
    updated_memories: list[Memory]
    new_problems: list[Problem]
    updated_problems: list[Problem]
