import random
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.prompts.prompt_registry import PromptRegistry
from kaoyan_agent.schemas.motivation import (
    DailySignOutput,
    RandomTaskOutput,
    SoothingTaskOutput,
)
from kaoyan_agent.services.llm_client import run_structured_agent


SIGN_LEVELS = ["top", "good", "steady", "small", "calm"]


def int_between(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


class MotivationAgent:
    def __init__(
        self,
        settings: Optional[Settings] = None,
        prompt_registry: Optional[PromptRegistry] = None,
    ):
        self.settings = settings
        self.prompt_registry = prompt_registry or PromptRegistry()

    def generate_daily_sign(self) -> Dict[str, Any]:
        fallback = random.choice(
            [
                {
                    "sign_level": "steady",
                    "sign_text": "Start small and keep the rhythm.",
                    "today_advice": "Finish one 15-minute task before deciding the next move.",
                    "action": "Pick the shortest task from today's board.",
                },
                {
                    "sign_level": "good",
                    "sign_text": "Stability comes before speed.",
                    "today_advice": "Split the most delayed task into two smaller actions.",
                    "action": "Review one mistake card and mark the reason.",
                },
                {
                    "sign_level": "calm",
                    "sign_text": "Compare less; return to the problem in hand.",
                    "today_advice": "Track actual completed work only.",
                    "action": "Do one 5-minute low-barrier starter task.",
                },
            ]
        )
        try:
            output = self.generate_structured(
                prompt=self.prompt_registry.get("motivation.daily_sign"),
                system_prompt=self.prompt_registry.get("motivation.system"),
                response_format=DailySignOutput,
                temperature=0.7,
            )
            return self.normalize_sign(output.model_dump(), fallback)
        except Exception as exc:
            result = self.normalize_sign(fallback, fallback)
            result["generation_error"] = str(exc)
            return result

    def generate_random_task(self) -> Dict[str, Any]:
        fallback = random.choice(
            [
                {
                    "title": "Review one recent mistake",
                    "subject": "mixed",
                    "estimated_minutes": 15,
                    "reason": "A short task can restore learning momentum.",
                },
                {
                    "title": "Write down three fragile knowledge points",
                    "subject": "mixed",
                    "estimated_minutes": 10,
                    "reason": "Make vague gaps visible before planning intervention.",
                },
                {
                    "title": "Do one basic problem from the current chapter",
                    "subject": "mixed",
                    "estimated_minutes": 12,
                    "reason": "Use a short task to test whether you can enter study mode.",
                },
            ]
        )
        try:
            output = self.generate_structured(
                prompt=self.prompt_registry.get("motivation.random_task"),
                system_prompt=self.prompt_registry.get("motivation.system"),
                response_format=RandomTaskOutput,
                temperature=0.5,
            )
            return self.normalize_task(output.model_dump(), fallback, max_minutes=20)
        except Exception as exc:
            result = self.normalize_task(fallback, fallback, max_minutes=20)
            result["generation_error"] = str(exc)
            return result

    def generate_soothing_task(self, user_state: str) -> Dict[str, Any]:
        fallback = {
            "title": "Open the review pool and read only one mistake reason",
            "subject": "low-energy start",
            "estimated_minutes": 3,
            "reason": "When energy is low, use a small action instead of a large plan.",
        }
        prompt = self.prompt_registry.render(
            "motivation.soothing_task",
            {"user_state": user_state},
        )
        try:
            output = self.generate_structured(
                prompt=prompt,
                system_prompt=self.prompt_registry.get("motivation.soothing_system"),
                response_format=SoothingTaskOutput,
                temperature=0.5,
            )
            return self.normalize_task(output.model_dump(), fallback, max_minutes=10)
        except Exception as exc:
            result = self.normalize_task(fallback, fallback, max_minutes=10)
            result["generation_error"] = str(exc)
            return result

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str,
        response_format: Type[BaseModel],
        temperature: float,
    ) -> BaseModel:
        return run_structured_agent(
            response_format,
            prompt,
            system_prompt=system_prompt,
            settings=self.settings,
            temperature=temperature,
        )

    def normalize_sign(
        self,
        sign: Dict[str, Any],
        fallback: Dict[str, Any],
    ) -> Dict[str, Any]:
        level = str(sign.get("sign_level") or "").strip()
        if level not in SIGN_LEVELS:
            level = fallback["sign_level"]
        return {
            "sign_level": level,
            "sign_text": str(sign.get("sign_text") or fallback["sign_text"]).strip(),
            "today_advice": str(
                sign.get("today_advice") or fallback["today_advice"]
            ).strip(),
            "action": str(sign.get("action") or fallback["action"]).strip(),
        }

    def normalize_task(
        self,
        task: Dict[str, Any],
        fallback: Dict[str, Any],
        max_minutes: int,
    ) -> Dict[str, Any]:
        return {
            "title": str(task.get("title") or fallback["title"]).strip(),
            "subject": str(task.get("subject") or fallback["subject"]).strip(),
            "estimated_minutes": int_between(
                task.get("estimated_minutes"),
                fallback["estimated_minutes"],
                1,
                max_minutes,
            ),
            "reason": str(task.get("reason") or fallback["reason"]).strip(),
        }


InterventionAgent = MotivationAgent
