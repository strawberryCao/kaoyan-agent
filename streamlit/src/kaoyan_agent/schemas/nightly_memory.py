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
ProblemStatus = Literal["open", "watching", "resolved", "ignored", "archived"]
MemoryType = Literal[
    "episodic",
    "semantic",
    "user_profile",
    "preference",
    "learning_status",
    "learning_state",
    "weakness",
    "mistake_pattern",
    "intervention_result",
    "project_state",
    "strategy",
]
MemoryOperation = Literal["insert", "update", "merge", "skip"]
ProblemOperation = Literal["insert", "update", "merge", "skip"]
SkillOperation = Literal["insert", "update", "merge", "skip"]
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
    subject: str = ""
    source_event_ids: list[int] = Field(default_factory=list)


class EvidenceRef(StrictNightlyModel):
    source_type: str = Field(default="raw_event", min_length=1)
    source_id: int | None = None
    quote: str = ""
    note: str = ""


class EpisodicMemory(StrictNightlyModel):
    title: str = ""
    content: str = Field(min_length=1)
    event_date: str = ""
    evidence_event_ids: list[int] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    event_type: str = ""
    subject: str = ""
    occurred_at: str = ""
    importance: int = Field(default=3, ge=1, le=5)
    source_event_ids: list[int] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class SemanticMemory(StrictNightlyModel):
    title: str = ""
    content: str = Field(min_length=1)
    category: str = ""
    evidence_event_ids: list[int] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    subject: str = ""
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class DailyGraphNode(StrictNightlyModel):
    node_key: str = Field(min_length=1)
    node_type: Literal[
        "raw_event",
        "episodic_memory",
        "semantic_memory",
        "problem",
        "skill",
        "action",
        "daily_memory_graph",
        "other",
    ] = "other"
    title: str = ""
    content: str = ""
    ref_type: str = ""
    ref_id: int | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    metadata: dict = Field(default_factory=dict)


class DailyGraphEdge(StrictNightlyModel):
    source_node_key: str = Field(min_length=1)
    target_node_key: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    weight: float = Field(default=1.0, ge=0, le=1)
    evidence_event_ids: list[int] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class EvidenceLink(StrictNightlyModel):
    source_type: str = "raw_event"
    source_id: int | None = None
    target_type: str = ""
    target_key: str = ""
    relation_type: str = "EVIDENCE_OF"
    quote: str = ""
    note: str = ""


class GraphNode(StrictNightlyModel):
    node_id: str = Field(min_length=1)
    node_type: Literal[
        "raw_event",
        "episode",
        "semantic_candidate",
        "memory_candidate",
        "problem_candidate",
        "skill_candidate",
        "memory",
        "problem",
        "skill",
        "daily_graph",
        "other",
    ] = "other"
    title: str = ""
    content: str | dict = ""
    ref_type: str = ""
    ref_id: int | None = None
    metadata: dict = Field(default_factory=dict)


class GraphEdge(StrictNightlyModel):
    source: str = Field(min_length=1)
    target: str = Field(min_length=1)
    relation_type: str = Field(min_length=1)
    weight: float = Field(default=1.0, ge=0, le=1)
    metadata: dict = Field(default_factory=dict)


class DailyMemoryGraphOutput(StrictNightlyModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    summary: str = ""


class DiscoveredProblem(StrictNightlyModel):
    operation: ProblemOperation = "insert"
    problem_type: ProblemType
    subject: str = ""
    description: str = Field(min_length=1)
    evidence: list[str] = Field(default_factory=list, min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    root_cause: str = ""
    severity: int = Field(ge=1, le=5)
    confidence: float = Field(ge=0, le=1)
    value_score: int = Field(ge=1, le=5)
    suggested_action: str = ""
    status: ProblemStatus = "open"
    merge_key: str = ""
    target_problem_id: int | None = None
    reason: str = ""


class MemoryUpdate(StrictNightlyModel):
    operation: MemoryOperation
    memory_type: MemoryType
    content: str = Field(min_length=1)
    importance: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(ge=0, le=1)
    merge_key: str = ""
    reason: str = ""
    status: Literal["active", "archived", "conflict", "pending_confirm"] = "active"
    valid_from: str = ""
    subject: str = ""
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    target_memory_id: int | None = None


class SkillMemoryUpdate(StrictNightlyModel):
    operation: SkillOperation = "insert"
    skill_name: str = Field(min_length=1)
    description: str = ""
    trigger: dict = Field(default_factory=dict)
    procedure: dict = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0, le=1)
    effectiveness_score: float = Field(default=0.0, ge=0, le=1)
    status: Literal["active", "archived", "pending_confirm"] = "active"
    evidence: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    merge_key: str = ""
    target_skill_id: int | None = None
    reason: str = ""


class NextAction(StrictNightlyModel):
    action_type: ActionType
    content: str = Field(min_length=1)
    related_problem: str = ""
    priority: int = Field(ge=1, le=5)


class NightlyMemoryUpdateOutput(StrictNightlyModel):
    daily_summary: str
    key_events: list[KeyEvent] = Field(default_factory=list)
    episodic_memories: list[EpisodicMemory] = Field(default_factory=list)
    semantic_memories: list[SemanticMemory] = Field(default_factory=list)
    daily_graph_nodes: list[DailyGraphNode] = Field(default_factory=list)
    daily_graph_edges: list[DailyGraphEdge] = Field(default_factory=list)
    daily_memory_graph: DailyMemoryGraphOutput = Field(default_factory=DailyMemoryGraphOutput)
    discovered_problems: list[DiscoveredProblem] = Field(default_factory=list)
    candidate_problems: list[DiscoveredProblem] = Field(default_factory=list)
    evidence_links: list[EvidenceLink] = Field(default_factory=list)
    memory_updates: list[MemoryUpdate] = Field(default_factory=list)
    skill_observations: list[SkillMemoryUpdate] = Field(default_factory=list)
    skill_updates: list[SkillMemoryUpdate] = Field(default_factory=list)
    next_actions: list[NextAction] = Field(default_factory=list)


class NightlyMemoryExtraction(NightlyMemoryUpdateOutput):
    """Formal nightly extraction contract; old output class remains the alias surface."""


