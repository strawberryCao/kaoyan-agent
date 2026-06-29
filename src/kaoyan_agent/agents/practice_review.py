from typing import Any, Dict, Optional

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.prompts.prompt_registry import PromptRegistry
from kaoyan_agent.schemas.practice_review import PracticeReviewCard
from kaoyan_agent.services.llm_client import run_structured_agent


ALLOWED_MISTAKE_REASONS = {
    "concept_gap",
    "method_gap",
    "calculation_error",
    "careless_error",
    "memory_gap",
    "expression_gap",
    "unknown",
}

MISTAKE_REASON_LABELS = {
    "concept_gap": "concept gap",
    "method_gap": "method transfer gap",
    "calculation_error": "calculation error",
    "careless_error": "careless review",
    "memory_gap": "memory gap",
    "expression_gap": "expression gap",
    "unknown": "unknown",
}


def clamp_priority(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 1
    return max(1, min(5, number))


def normalize_text_list(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


class PracticeReviewAgent:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        prompt_registry: Optional[PromptRegistry] = None,
    ):
        self.settings = settings
        self.prompt_registry = prompt_registry or PromptRegistry()

    def generate_card(
        self,
        subject: str,
        chapter: str,
        question: str,
        user_reason: str = "",
    ) -> Dict[str, Any]:
        fallback = self.build_fallback_card(subject, chapter, question, user_reason)
        prompt = self.prompt_registry.render(
            "practice_review.card",
            {
                "subject": subject,
                "chapter": chapter,
                "question": question,
                "user_reason": user_reason,
            },
        )
        system_prompt = self.prompt_registry.get("practice_review.system")
        try:
            card = self.generate_langchain_card(
                prompt=prompt,
                system_prompt=system_prompt,
            )
            return self.normalize_card(card.model_dump(), fallback)
        except Exception as exc:
            result = self.normalize_card(fallback, fallback)
            result["generation_error"] = str(exc)
            return result

    def generate_langchain_card(
        self,
        prompt: str,
        system_prompt: str,
    ) -> PracticeReviewCard:
        return run_structured_agent(
            PracticeReviewCard,
            prompt,
            system_prompt=system_prompt,
            settings=self.settings,
            temperature=0.2,
        )

    def build_fallback_card(
        self,
        subject: str,
        chapter: str,
        question: str,
        user_reason: str = "",
    ) -> Dict[str, Any]:
        subject_text = subject.strip() or "current subject"
        chapter_text = chapter.strip() or "current chapter"
        reason = self.infer_reason(user_reason or question)
        return {
            "knowledge_points": f"{subject_text} / {chapter_text} core concept and typical pattern",
            "mistake_reason": reason,
            "analysis": (
                "Fallback review card: the system recorded this question and "
                "kept the user's evidence. Review the mistake reason first, "
                "then verify improvement with a nearby problem."
            ),
            "review_priority": 3,
        }

    def infer_reason(self, text: str) -> str:
        lower = (text or "").lower()
        if any(keyword in lower for keyword in ["calculate", "calculation", "symbol"]):
            return "calculation_error"
        if any(keyword in lower for keyword in ["careless", "misread", "review"]):
            return "careless_error"
        if any(keyword in lower for keyword in ["forget", "memory", "recall"]):
            return "memory_gap"
        if any(keyword in lower for keyword in ["method", "transfer", "approach"]):
            return "method_gap"
        if any(keyword in lower for keyword in ["concept", "definition", "understand"]):
            return "concept_gap"
        if any(keyword in lower for keyword in ["write", "expression", "format"]):
            return "expression_gap"
        return "unknown"

    def normalize_card(
        self,
        card: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        reason = str(card.get("mistake_reason") or "").strip()
        if reason not in ALLOWED_MISTAKE_REASONS:
            reason = fallback["mistake_reason"]

        return {
            "knowledge_points": normalize_text_list(
                card.get("knowledge_points") or fallback["knowledge_points"]
            ),
            "mistake_reason": reason,
            "analysis": str(card.get("analysis") or fallback["analysis"]).strip(),
            "review_priority": clamp_priority(
                card.get("review_priority", fallback["review_priority"])
            ),
        }


MistakeReviewAgent = PracticeReviewAgent
