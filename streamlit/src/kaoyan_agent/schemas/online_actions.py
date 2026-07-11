from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict


ACTION_INTENTS = {
    "explicit_action",
    "answer_first_then_suggest",
    "suggest_action",
    "need_clarification",
    "no_action",
}


@dataclass
class ActionIntentDecision:
    intent: str
    action_type: str = ""
    reason: str = ""
    parsed: Dict[str, Any] = field(default_factory=dict)
    missing_fields: list[str] = field(default_factory=list)
    requires_chat_answer: bool = False
    should_execute: bool = False
    should_create_pending: bool = False

    def __post_init__(self) -> None:
        if self.intent not in ACTION_INTENTS:
            self.intent = "no_action"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OnlineActionResult:
    action_type: str
    status: str
    user_message: str
    data: Dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    debug: Dict[str, Any] = field(default_factory=dict)
    intent: str = ""
    pending_action_id: int | None = None
    requires_chat_answer: bool = False

    @property
    def handled(self) -> bool:
        return bool(self.action_type) and self.status in {
            "success",
            "warning",
            "needs_input",
            "unsupported",
            "failed",
            "idempotent",
            "pending_confirmation",
        }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
