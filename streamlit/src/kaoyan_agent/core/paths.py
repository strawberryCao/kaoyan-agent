from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "app.db"

SCHEMA_PATH = PACKAGE_ROOT / "db" / "schema.sql"

PROMPTS_DIR = PACKAGE_ROOT / "prompts"
NIGHTLY_MEMORY_PROMPT_PATH = PROMPTS_DIR / "nightly_memory_update_prompt.txt"
