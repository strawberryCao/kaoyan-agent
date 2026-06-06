import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kaoyan_agent.core.paths import DB_PATH, PROJECT_ROOT

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        return False


load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    llm_api_key: str
    llm_base_url: Optional[str]
    llm_model: str
    database_path: Path = DB_PATH


def get_settings() -> Settings:
    return Settings(
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip() or None,
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini").strip(),
    )

