from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RetrievedItem:
    source_type: str
    source_id: Optional[int]
    content: str
    score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentRequest:
    request_id: str
    user_id: str
    session_id: Optional[int]
    input_text: str
    context: Dict[str, Any] = field(default_factory=dict)
    retrieved_items: List[RetrievedItem] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentResponse:
    text: str
    structured_data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    next_actions: List[Dict[str, Any]] = field(default_factory=list)
    raw_response: str = ""
    parse_status: str = "ok"
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ToolRequest:
    tool_name: str
    arguments: Dict[str, Any]
    user_id: str = "default"
    session_id: Optional[int] = None
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ToolResult:
    tool_name: str
    status: str
    data: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RouterDecision:
    route: str = "chat"
    need_memory: bool = False
    need_search: bool = False
    need_file: bool = False
    need_tools: bool = False
    need_problem_discovery: bool = False
    need_plan: bool = False
    retrieval_weights: Dict[str, float] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OnlineSessionResult:
    session_id: int
    user_message_id: int
    assistant_message_id: int
    user_event_id: int
    assistant_event_id: int
    assistant_text: str
    rewritten_query: str
    router_decision: RouterDecision
    retrieved_items: List[RetrievedItem] = field(default_factory=list)
    action_result: Optional[Dict[str, Any]] = None
    pending_action: Optional[Dict[str, Any]] = None
    agent_run_id: Optional[int] = None
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NightlyWorkflowResult:
    review_id: int
    review_date: str
    parse_status: str
    sessions_count: int
    conversations_count: int
    raw_events_count: int
    inserted_problem_ids: List[int] = field(default_factory=list)
    inserted_memory_ids: List[int] = field(default_factory=list)
    inserted_skill_ids: List[int] = field(default_factory=list)
    daily_memory_graph_id: Optional[int] = None
    gate_results: List[Dict[str, Any]] = field(default_factory=list)
    error_message: str = ""
    result: Any = field(default_factory=dict)
    validation_errors: List[Dict[str, Any]] = field(default_factory=list)
    normalization_diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    candidate_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if hasattr(self.result, "model_dump"):
            data["result"] = self.result.model_dump()
        return data


