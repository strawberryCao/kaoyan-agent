from __future__ import annotations

from contextlib import closing
from typing import Any, Dict, List

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.db.database import get_connection, json_loads
from kaoyan_agent.services.embedding_client import EmbeddingClient
from kaoyan_agent.services.graph_store import GraphStore
from kaoyan_agent.services.vector_store import VectorStore


NO_VECTOR_MESSAGE = (
    "当前未启用可用的 Chroma 向量库，在线检索只能临时回退到轻量可解释检索："
    "关键词重叠 + 时间 + 有效性 + 热度。"
)
NO_GRAPH_MESSAGE = "当前未连接 Neo4j 图数据库，检索不会使用 graph_boost。"


class MemoryBackendAudit:
    def __init__(
        self,
        settings: Settings | None = None,
        vector_store: VectorStore | None = None,
        graph_store: GraphStore | None = None,
        embedding_client: EmbeddingClient | None = None,
    ):
        self.settings = settings or get_settings()
        self.embedding_client = embedding_client or EmbeddingClient(self.settings)
        self.vector_store = vector_store or VectorStore(self.settings, embedding_client=self.embedding_client)
        self.graph_store = graph_store or GraphStore(self.settings)

    def run(self) -> Dict[str, Any]:
        tables = self.list_tables()
        counts = {table: self.count_table(table) for table in tables}
        vector_status = self.vector_store.get_status()
        graph_status = self.graph_store.get_status()
        latest_review = self.latest_nightly_review(tables)
        sql_counts = {
            "raw_events": counts.get("raw_events", 0),
            "memories": counts.get("memories", 0),
            "problem_board": counts.get("problem_board", 0),
            "open_problems": self.count_open_problems(tables),
            "nightly_reviews": counts.get("nightly_reviews", 0),
            "mistake_cards": counts.get("mistake_cards", 0),
            "study_tasks": counts.get("study_tasks", 0),
            "focus_sessions": counts.get("focus_sessions", 0),
            "skill_memories": counts.get("skill_memories", 0),
        }
        sql_status = {
            "backend": "sqlite",
            "available": True,
            "database_tables": len(tables),
            "counts": sql_counts,
        }
        graph_available = bool(graph_status.get("connected") or graph_status.get("available"))
        return {
            "sql": sql_status,
            "vector": vector_status,
            "graph": graph_status,
            "embedding": self.embedding_client.get_status(),
            "counts": {
                **sql_counts,
                "daily_memory_graphs": counts.get("daily_memory_graphs", 0),
                "daily_graph_nodes": counts.get("daily_graph_nodes", 0),
                "daily_graph_edges": counts.get("daily_graph_edges", 0),
                "global_graph_nodes": counts.get("global_graph_nodes", 0),
                "global_graph_edges": counts.get("global_graph_edges", 0),
                "sqlite_graph_nodes": counts.get("graph_nodes", 0),
                "sqlite_graph_edges": counts.get("graph_edges", 0),
                "sqlite_embeddings": self.count_embeddings(tables),
                "episodic_memories": self.count_memories_by_type(tables, "episodic"),
                "semantic_memories": self.count_memories_by_type(tables, "semantic"),
            },
            "tables": sorted(tables),
            "vector_backend_type": vector_status.get("backend", "none"),
            "vector_backend_enabled": bool(vector_status.get("enabled")),
            "vector_backend_available": bool(vector_status.get("available")),
            "vector_message": "" if vector_status.get("available") else NO_VECTOR_MESSAGE,
            "retriever_type": "hybrid" if vector_status.get("available") else "keyword_overlap",
            "retriever_formula": (
                "final_score = w1 * vector_similarity + w2 * time_score + "
                "w3 * effectiveness_score + w4 * heat_score + graph_boost"
            ),
            "graph_backend_type": graph_status.get("backend", "none"),
            "graph_backend_enabled": bool(graph_status.get("enabled")),
            "graph_backend_available": graph_available,
            "graph_backend_connected": bool(graph_status.get("connected")),
            "graph_message": "" if graph_available else NO_GRAPH_MESSAGE,
            "latest_nightly_review": latest_review,
            "skill_memory_enabled": counts.get("skill_memories", 0) > 0,
            "requirements_signals": self.scan_requirements(),
        }

    def list_tables(self) -> set[str]:
        with closing(get_connection()) as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        return {str(row["name"]) for row in rows}

    def count_table(self, table: str) -> int:
        try:
            with closing(get_connection()) as connection:
                return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except Exception:
            return 0

    def count_open_problems(self, tables: set[str]) -> int:
        if "problem_board" not in tables:
            return 0
        with closing(get_connection()) as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM problem_board WHERE status IN ('open', 'watching')"
                ).fetchone()[0]
            )

    def count_embeddings(self, tables: set[str]) -> int:
        total = 0
        for table in ("memories", "problem_board", "global_memory_nodes", "skill_memories", "graph_nodes"):
            if table not in tables:
                continue
            try:
                with closing(get_connection()) as connection:
                    rows = connection.execute(
                        f"SELECT embedding_json FROM {table} "
                        "WHERE embedding_json IS NOT NULL AND embedding_json != ''"
                    ).fetchall()
                for row in rows:
                    embedding = json_loads(row["embedding_json"], [])
                    if isinstance(embedding, list) and embedding:
                        total += 1
            except Exception:
                continue
        return total

    def latest_nightly_review(self, tables: set[str]) -> Dict[str, Any]:
        if "nightly_reviews" not in tables:
            return {}
        with closing(get_connection()) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    review_date,
                    parse_status,
                    error_message,
                    inserted_counts_json,
                    index_sync_status_json,
                    created_at
                FROM nightly_reviews
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return {}
        review = dict(row)
        review["inserted_counts"] = json_loads(review.get("inserted_counts_json", "{}"), {})
        review["index_sync_status"] = json_loads(review.get("index_sync_status_json", "{}"), {})
        return review

    def count_memories_by_type(self, tables: set[str], memory_type: str) -> int:
        if "memories" not in tables:
            return 0
        with closing(get_connection()) as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM memories WHERE memory_type = ?",
                    (memory_type,),
                ).fetchone()[0]
            )

    def scan_requirements(self) -> List[str]:
        requirements = self.settings.database_path.parent.parent / "requirements.txt"
        if not requirements.exists():
            return []
        text = requirements.read_text(encoding="utf-8", errors="ignore").lower()
        signals = []
        for name in ("chromadb", "neo4j", "faiss", "qdrant", "pgvector"):
            if name in text:
                signals.append(name)
        return sorted(set(signals))
