from dataclasses import dataclass
from typing import Optional

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.prompts.prompt_registry import PromptRegistry
from kaoyan_agent.services.llm_client import LLMClient


@dataclass
class AppContainer:
    settings: Settings
    prompt_registry: PromptRegistry
    llm_client: Optional[LLMClient] = None

    @classmethod
    def create(cls, settings: Optional[Settings] = None) -> "AppContainer":
        settings = settings or get_settings()
        prompt_registry = PromptRegistry()
        try:
            llm_client = LLMClient(settings)
        except Exception:
            llm_client = None
        return cls(
            settings=settings,
            prompt_registry=prompt_registry,
            llm_client=llm_client,
        )


