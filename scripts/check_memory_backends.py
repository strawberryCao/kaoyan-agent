from __future__ import annotations

import json
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kaoyan_agent.core.settings import get_settings  # noqa: E402
from kaoyan_agent.db import database  # noqa: E402
from kaoyan_agent.db.database import get_connection  # noqa: E402
from kaoyan_agent.services.embedding_client import EmbeddingClient  # noqa: E402
from kaoyan_agent.services.graph_store import GraphStore  # noqa: E402
from kaoyan_agent.services.vector_store import VectorStore  # noqa: E402


def count_table(table: str) -> int:
    try:
        with closing(get_connection()) as connection:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except Exception:
        return 0


def main() -> None:
    settings = get_settings()
    database.init_db()

    embedding_client = EmbeddingClient(settings)
    embedding_probe = embedding_client.encode("考研记忆检索测试")
    vector_store = VectorStore(settings, embedding_client=embedding_client)
    graph_store = GraphStore(settings)

    output: dict[str, Any] = {
        "sqlite": {
            "database_path": str(settings.database_path),
            "raw_events": count_table("raw_events"),
            "memories": count_table("memories"),
            "problem_board": count_table("problem_board"),
            "mistake_cards": count_table("mistake_cards"),
            "study_tasks": count_table("study_tasks"),
            "focus_sessions": count_table("focus_sessions"),
        },
        "embedding": {
            **embedding_client.get_status(),
            "probe_vector_length": len(embedding_probe or []),
        },
        "chroma": vector_store.get_status(),
        "neo4j": graph_store.get_status(),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()

