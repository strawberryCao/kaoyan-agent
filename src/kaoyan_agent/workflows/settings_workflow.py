from typing import Any

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.repositories.memory_repository import MemoryRepository


class SettingsWorkflow:
    """Read settings-page data without exposing database compatibility details."""

    workflow_name = "settings"

    def __init__(self, memory_repository: MemoryRepository | None = None):
        self.memory_repository = memory_repository or MemoryRepository()

    def load_settings(
        self,
        settings: Settings,
        memory_limit: int = 100,
    ) -> dict[str, Any]:
        return {
            "memories": self.memory_repository.list(limit=memory_limit),
            "model": settings.llm_model,
            "database_path": str(settings.database_path),
        }
