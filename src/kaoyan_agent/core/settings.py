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
    focus_local_model_path: Optional[Path] = None
    focus_local_model_confidence: float = 0.35


def get_settings() -> Settings:
    model_path = os.getenv("FOCUS_LOCAL_MODEL_PATH", "").strip()
    try:
        model_confidence = float(os.getenv("FOCUS_LOCAL_MODEL_CONFIDENCE", "0.35"))
    except ValueError:
        model_confidence = 0.35

    return Settings(
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip() or None,
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini").strip(),
        focus_local_model_path=Path(model_path) if model_path else None,
        focus_local_model_confidence=max(0.0, min(1.0, model_confidence)),
    )

