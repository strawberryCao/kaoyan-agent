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
    embedding_provider: str = "siliconflow"
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    embedding_batch_size: int = 16
    embedding_timeout_seconds: float = 20.0
    vector_backend: str = "chroma"
    chroma_persist_dir: Path = PROJECT_ROOT / "data" / "chroma"
    graph_backend: str = "neo4j"
    graph_sync_raw_events: bool = False
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = ""
    focus_local_model_path: Optional[Path] = None
    focus_local_model_confidence: float = 0.35
    yolo_focus_weights_path: Optional[Path] = None
    yolo_focus_camera_id: int = 0
    yolo_focus_confidence_threshold: float = 0.5
    yolo_focus_inference_fps: int = 3


def get_settings() -> Settings:
    focus_model_path = os.getenv("FOCUS_LOCAL_MODEL_PATH", "").strip()
    try:
        focus_model_confidence = float(
            os.getenv("FOCUS_LOCAL_MODEL_CONFIDENCE", "0.35") or 0.35
        )
    except ValueError:
        focus_model_confidence = 0.35
    yolo_weights_path = os.getenv("YOLO_FOCUS_WEIGHTS_PATH", "").strip()
    try:
        yolo_camera_id = int(os.getenv("YOLO_FOCUS_CAMERA_ID", "0") or 0)
    except ValueError:
        yolo_camera_id = 0
    try:
        yolo_confidence = float(os.getenv("YOLO_FOCUS_CONFIDENCE_THRESHOLD", "0.5") or 0.5)
    except ValueError:
        yolo_confidence = 0.5
    try:
        yolo_fps = int(os.getenv("YOLO_FOCUS_INFERENCE_FPS", "3") or 3)
    except ValueError:
        yolo_fps = 3

    return Settings(
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip() or None,
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini").strip(),
        embedding_provider=os.getenv("EMBEDDING_PROVIDER", "siliconflow").strip(),
        embedding_api_key=os.getenv("EMBEDDING_API_KEY", "").strip(),
        embedding_base_url=os.getenv(
            "EMBEDDING_BASE_URL",
            "https://api.siliconflow.cn/v1",
        ).strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3").strip(),
        embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "16") or 16),
        embedding_timeout_seconds=float(
            os.getenv("EMBEDDING_TIMEOUT_SECONDS", "20") or 20
        ),
        vector_backend=os.getenv("VECTOR_BACKEND", "chroma").strip().lower() or "chroma",
        chroma_persist_dir=Path(
            os.getenv("CHROMA_PERSIST_DIR", str(PROJECT_ROOT / "data" / "chroma")).strip()
            or PROJECT_ROOT / "data" / "chroma"
        ),
        graph_backend=os.getenv("GRAPH_BACKEND", "neo4j").strip().lower() or "neo4j",
        graph_sync_raw_events=(os.getenv("GRAPH_SYNC_RAW_EVENTS", "false").strip().lower() in {"1", "true", "yes", "on"}),
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687").strip(),
        neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j").strip(),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "").strip(),
        focus_local_model_path=Path(focus_model_path) if focus_model_path else None,
        focus_local_model_confidence=max(0.0, min(1.0, focus_model_confidence)),
        yolo_focus_weights_path=Path(yolo_weights_path) if yolo_weights_path else None,
        yolo_focus_camera_id=max(0, yolo_camera_id),
        yolo_focus_confidence_threshold=max(0.0, min(1.0, yolo_confidence)),
        yolo_focus_inference_fps=max(1, min(30, yolo_fps)),
    )

