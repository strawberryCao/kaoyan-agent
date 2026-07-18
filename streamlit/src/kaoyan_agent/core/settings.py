import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from kaoyan_agent.core.paths import DATA_DIR, DB_PATH, PROJECT_ROOT

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
    chroma_persist_dir: Path = DATA_DIR / "chroma"
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
    yolo_person_weights_path: Path = (
        PROJECT_ROOT / "models" / "person_presence" / "yolov8n.pt"
    )
    yolo_person_confidence_threshold: float = 0.35
    focus_phone_confidence_threshold: float = 0.35
    focus_visual_evidence_threshold: float = 0.55
    focus_presence_focus_confidence_threshold: float = 0.65
    yolo_away_confirm_seconds: int = 10
    yolo_behavior_window_seconds: int = 3
    focus_report_min_coverage: float = 0.8


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
        yolo_confidence = float(
            os.getenv("YOLO_FOCUS_CONFIDENCE_THRESHOLD", "0.5") or 0.5
        )
    except ValueError:
        yolo_confidence = 0.5
    try:
        yolo_fps = int(os.getenv("YOLO_FOCUS_INFERENCE_FPS", "3") or 3)
    except ValueError:
        yolo_fps = 3
    person_weights_path = os.getenv(
        "YOLO_PERSON_WEIGHTS_PATH",
        "models/person_presence/yolov8n.pt",
    ).strip()
    try:
        person_confidence = float(
            os.getenv("YOLO_PERSON_CONFIDENCE_THRESHOLD", "0.35") or 0.35
        )
    except ValueError:
        person_confidence = 0.35
    try:
        phone_confidence = float(
            os.getenv("FOCUS_PHONE_CONFIDENCE_THRESHOLD", "0.35") or 0.35
        )
    except ValueError:
        phone_confidence = 0.35
    try:
        visual_evidence_threshold = float(
            os.getenv("FOCUS_VISUAL_EVIDENCE_THRESHOLD", "0.55") or 0.55
        )
    except ValueError:
        visual_evidence_threshold = 0.55
    try:
        presence_focus_threshold = float(
            os.getenv("FOCUS_PRESENCE_FOCUS_CONFIDENCE_THRESHOLD", "0.65") or 0.65
        )
    except ValueError:
        presence_focus_threshold = 0.65
    try:
        away_confirm_seconds = int(os.getenv("YOLO_AWAY_CONFIRM_SECONDS", "10") or 10)
    except ValueError:
        away_confirm_seconds = 10
    try:
        behavior_window_seconds = int(
            os.getenv("YOLO_BEHAVIOR_WINDOW_SECONDS", "3") or 3
        )
    except ValueError:
        behavior_window_seconds = 3
    try:
        report_min_coverage = float(
            os.getenv("FOCUS_REPORT_MIN_COVERAGE", "0.8") or 0.8
        )
    except ValueError:
        report_min_coverage = 0.8

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
        vector_backend=os.getenv("VECTOR_BACKEND", "chroma").strip().lower()
        or "chroma",
        chroma_persist_dir=Path(
            os.getenv(
                "CHROMA_PERSIST_DIR", str(DATA_DIR / "chroma")
            ).strip()
            or DATA_DIR / "chroma"
        ),
        graph_backend=os.getenv("GRAPH_BACKEND", "neo4j").strip().lower() or "neo4j",
        graph_sync_raw_events=(
            os.getenv("GRAPH_SYNC_RAW_EVENTS", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        ),
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687").strip(),
        neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j").strip(),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "").strip(),
        focus_local_model_path=Path(focus_model_path) if focus_model_path else None,
        focus_local_model_confidence=max(0.0, min(1.0, focus_model_confidence)),
        yolo_focus_weights_path=Path(yolo_weights_path) if yolo_weights_path else None,
        yolo_focus_camera_id=max(0, yolo_camera_id),
        yolo_focus_confidence_threshold=max(0.0, min(1.0, yolo_confidence)),
        yolo_focus_inference_fps=max(1, min(30, yolo_fps)),
        yolo_person_weights_path=(
            Path(person_weights_path)
            if Path(person_weights_path).is_absolute()
            else PROJECT_ROOT / person_weights_path
        ),
        yolo_person_confidence_threshold=max(0.0, min(1.0, person_confidence)),
        focus_phone_confidence_threshold=max(0.0, min(1.0, phone_confidence)),
        focus_visual_evidence_threshold=max(0.0, min(1.0, visual_evidence_threshold)),
        focus_presence_focus_confidence_threshold=max(
            0.0, min(1.0, presence_focus_threshold)
        ),
        yolo_away_confirm_seconds=max(3, min(120, away_confirm_seconds)),
        yolo_behavior_window_seconds=max(1, min(10, behavior_window_seconds)),
        focus_report_min_coverage=max(0.0, min(1.0, report_min_coverage)),
    )
