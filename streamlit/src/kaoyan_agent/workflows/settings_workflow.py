from typing import Any

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.repositories.memory_repository import MemoryRepository
from kaoyan_agent.repositories.skill_memory_repository import SkillMemoryRepository


class SettingsWorkflow:
    """Read settings-page data without exposing database compatibility details."""

    workflow_name = "settings"

    def __init__(
        self,
        memory_repository: MemoryRepository | None = None,
        skill_repository: SkillMemoryRepository | None = None,
    ):
        self.memory_repository = memory_repository or MemoryRepository()
        self.skill_repository = skill_repository or SkillMemoryRepository()

    def load_settings(
        self,
        settings: Settings,
        memory_limit: int = 100,
    ) -> dict[str, Any]:
        return {
            "memories": self.memory_repository.list(limit=memory_limit),
            "skill_memories": self.skill_repository.list(limit=memory_limit),
            "model": settings.llm_model,
            "database_path": str(settings.database_path),
            "embedding_provider": settings.embedding_provider,
            "embedding_model": settings.embedding_model,
        }
