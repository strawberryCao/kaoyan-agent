import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.db import database
from kaoyan_agent.memory.retriever import MemoryRetriever
from kaoyan_agent.repositories.memory_repository import MemoryRepository
from kaoyan_agent.repositories.problem_repository import ProblemRepository
from kaoyan_agent.schemas.contracts import RouterDecision
from kaoyan_agent.services.embedding_client import EmbeddingClient
from kaoyan_agent.services.graph_store import GraphStore, Neo4jGraphStore
from kaoyan_agent.services.memory_backend_audit import MemoryBackendAudit
from kaoyan_agent.services.vector_store import VectorStore
from scripts.backfill_memory_indexes import backfill


class FakeEmbeddingClient:
    last_error = ""

    def encode(self, text):
        return [0.1, 0.2, 0.3]


class FakeCollection:
    def __init__(self, query_result=None):
        self.upserts = []
        self.query_result = query_result if query_result is not None else {
            "ids": [["memory:1"]],
            "documents": [["integral substitution memory"]],
            "metadatas": [[{"source_type": "memory", "source_id": 1, "project_id": 1}]],
            "distances": [[0.2]],
        }

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def query(self, **kwargs):
        return self.query_result

    def count(self):
        return len(self.upserts)


class FakeVectorAvailable:
    def __init__(self, source_id):
        self.source_id = source_id

    def get_status(self):
        return {"backend": "chroma", "enabled": True, "available": True, "error": ""}

    def query(self, text, limit=8, project_id=None):
        return [
            {
                "source_type": "memory",
                "source_id": self.source_id,
                "content": "integral substitution memory",
                "vector_similarity": 0.91,
                "metadata": {"project_id": project_id or "", "updated_at": ""},
            }
        ]


class FakeVectorUnavailable:
    def get_status(self):
        return {"backend": "chroma", "enabled": True, "available": False, "error": "mock unavailable"}


class FakeStatusStore:
    def __init__(self, status):
        self.status = status

    def get_status(self):
        return self.status


class FakeBackfillVector:
    def __init__(self):
        self.calls = []

    def upsert_memory(self, memory):
        self.calls.append(("memory", memory.get("id")))
        return {"status": "success"}

    def upsert_problem(self, problem):
        self.calls.append(("problem", problem.get("id")))
        return {"status": "success"}

    def get_status(self):
        return {"backend": "chroma", "available": True, "collections": {"memories": 1, "problems": 1}}


class FakeBackfillGraph:
    def __init__(self):
        self.calls = []

    @staticmethod
    def node_key(ref_type, ref_id):
        return f"{ref_type}:{ref_id}"

    def upsert_node(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": "success"}

    def get_status(self):
        return {"backend": "neo4j", "connected": True, "node_count": len(self.calls), "edge_count": 0}


class MemoryBackendTest(unittest.TestCase):
    def run_in_db(self, callback, **settings_overrides):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                "",
                None,
                "test-model",
                database_path=Path(temp_dir) / "app.db",
                **settings_overrides,
            )
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                return callback(settings)

    def test_vector_store_upsert_query_and_status_with_mock_collection(self):
        collection = FakeCollection()
        empty_collection = FakeCollection(
            {
                "ids": [[]],
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
            }
        )
        settings = Settings("", None, "test-model", embedding_api_key="embedding-key")
        store = VectorStore(
            settings=settings,
            embedding_client=FakeEmbeddingClient(),
            collections={"memories": collection, "problems": empty_collection},
        )

        upsert = store.upsert_memory(
            {
                "id": 1,
                "project_id": 1,
                "content": "integral substitution memory",
                "memory_type": "strategy",
                "status": "active",
                "embedding": [0.1, 0.2, 0.3],
            }
        )
        results = store.query("integral", limit=3, project_id=1)
        status = store.get_status()

        self.assertEqual(upsert["status"], "success")
        self.assertEqual(status["backend"], "chroma")
        self.assertEqual(status["collection_count"], 1)
        self.assertEqual(status["collections"]["memories"], 1)
        self.assertEqual(status["collections"]["problems"], 0)
        self.assertEqual(results[0]["source_type"], "memory")
        self.assertAlmostEqual(results[0]["vector_similarity"], 0.8)

    def test_sqlite_graph_node_edge_neighbors_and_status(self):
        def scenario(settings):
            graph = GraphStore(settings)
            graph.upsert_node(
                node_key="memory:1",
                node_type="memory",
                ref_type="memory",
                ref_id=1,
                title="Memory 1",
            )
            graph.upsert_node(
                node_key="problem:2",
                node_type="problem",
                ref_type="problem",
                ref_id=2,
                title="Problem 2",
            )
            graph.upsert_edge(
                source_node_key="memory:1",
                target_node_key="problem:2",
                relation_type="relates_to",
            )
            neighbors = graph.get_neighbors("memory:1")
            status = graph.get_status()

            self.assertTrue(status["available"])
            self.assertEqual(status["node_count"], 2)
            self.assertEqual(status["edge_count"], 1)
            self.assertEqual(len(neighbors["edges"]), 1)
            self.assertEqual({node["node_key"] for node in neighbors["nodes"]}, {"memory:1", "problem:2"})

        self.run_in_db(scenario, graph_backend="sqlite_graph")

    def test_neo4j_graph_store_unconnected_returns_clear_error(self):
        settings = Settings(
            "",
            None,
            "test-model",
            graph_backend="neo4j",
            neo4j_uri="bolt://localhost:1",
            neo4j_username="neo4j",
            neo4j_password="password",
        )
        status = Neo4jGraphStore(settings).get_status()

        self.assertEqual(status["backend"], "neo4j")
        self.assertFalse(status["connected"])
        self.assertTrue(status["error"])

    def test_embedding_client_missing_key_is_unavailable(self):
        client = EmbeddingClient(Settings("", None, "test-model", embedding_api_key=""))
        vector = client.encode("test")
        status = client.get_status()

        self.assertEqual(vector, [])
        self.assertFalse(status["available"])
        self.assertIn("EMBEDDING_API_KEY", status["last_error"])

    def test_memory_retriever_uses_hybrid_when_vector_available(self):
        def scenario(settings):
            memory_id = MemoryRepository().create(
                {"content": "integral substitution memory", "importance": 4},
            )
            graph = GraphStore(settings)
            graph.upsert_node(node_key=f"memory:{memory_id}", node_type="memory", ref_type="memory", ref_id=memory_id)
            graph.upsert_node(node_key="problem:9", node_type="problem", ref_type="problem", ref_id=9)
            graph.upsert_edge(
                source_node_key=f"memory:{memory_id}",
                target_node_key="problem:9",
                relation_type="supports",
            )

            retriever = MemoryRetriever(
                vector_store=FakeVectorAvailable(memory_id),
                graph_store=graph,
            )
            items = retriever.retrieve("integral", RouterDecision(need_memory=True), limit=3)

            self.assertEqual(items[0].metadata["retrieval_backend"], "chroma_hybrid")
            self.assertTrue(items[0].metadata["vector_used"])
            self.assertTrue(items[0].metadata["graph_used"])
            self.assertEqual(items[0].metadata["vector_similarity"], 0.91)
            self.assertGreater(items[0].metadata["graph_boost"], 0)
            self.assertIn("graph_neighbors", items[0].metadata)

        self.run_in_db(scenario, graph_backend="sqlite_graph")

    def test_memory_retriever_falls_back_when_vector_unavailable(self):
        def scenario(settings):
            MemoryRepository().create(
                {"content": "linear algebra eigenvalue memory", "importance": 4},
            )
            retriever = MemoryRetriever(vector_store=FakeVectorUnavailable(), graph_store=GraphStore(settings))
            items = retriever.retrieve("eigenvalue", RouterDecision(need_memory=True), limit=3)

            self.assertTrue(items)
            self.assertEqual(items[0].metadata["retrieval_backend"], "keyword_overlap")
            self.assertIn("mock unavailable", items[0].metadata["fallback_reason"])

        self.run_in_db(scenario, graph_backend="sqlite_graph")

    def test_memory_backend_audit_reports_real_backend_statuses(self):
        def scenario(settings):
            audit = MemoryBackendAudit(
                settings=settings,
                vector_store=FakeStatusStore(
                    {
                        "backend": "chroma",
                        "enabled": True,
                        "available": True,
                        "persist_dir": "data/chroma",
                        "embedding_model": "mock-embedding",
                        "collection_count": 3,
                        "error": "",
                    }
                ),
                graph_store=GraphStore(settings),
            ).run()

            self.assertEqual(audit["sql"]["backend"], "sqlite")
            self.assertEqual(audit["vector_backend_type"], "chroma")
            self.assertTrue(audit["vector_backend_available"])
            self.assertEqual(audit["retriever_type"], "hybrid")
            self.assertEqual(audit["graph_backend_type"], "sqlite_graph")
            self.assertTrue(audit["graph_backend_available"])

        self.run_in_db(scenario, graph_backend="sqlite_graph")

    def test_memory_backend_audit_does_not_fake_disabled_or_neo4j_backend(self):
        def disabled(settings):
            audit = MemoryBackendAudit(settings=settings).run()
            self.assertEqual(audit["vector_backend_type"], "none")
            self.assertFalse(audit["vector_backend_available"])
            self.assertEqual(audit["graph_backend_type"], "none")
            self.assertFalse(audit["graph_backend_available"])

        self.run_in_db(disabled, vector_backend="none", graph_backend="none")

        def neo4j_unconfigured(settings):
            audit = MemoryBackendAudit(settings=settings).run()
            self.assertEqual(audit["graph_backend_type"], "neo4j")
            self.assertFalse(audit["graph_backend_available"])
            self.assertTrue(audit["graph"]["error"])

        self.run_in_db(neo4j_unconfigured, graph_backend="neo4j")

    def test_backfill_memory_indexes_runs_against_existing_sqlite_rows(self):
        def scenario(settings):
            MemoryRepository().create({"content": "memory for backfill", "importance": 4})
            ProblemRepository().create({"description": "problem for backfill", "status": "open"})
            fake_vector = FakeBackfillVector()
            fake_graph = FakeBackfillGraph()

            result = backfill(
                all_indexes=True,
                settings=settings,
                vector_store=fake_vector,
                graph_store=fake_graph,
            )
            dry_result = backfill(
                all_indexes=True,
                dry_run=True,
                settings=settings,
                vector_store=fake_vector,
                graph_store=fake_graph,
            )

            self.assertEqual(result["memory_count"], 1)
            self.assertEqual(result["problem_count"], 1)
            self.assertEqual(result["vector"]["success"], 2)
            self.assertEqual(result["graph"]["success"], 2)
            self.assertEqual(len(fake_vector.calls), 2)
            self.assertEqual(len(fake_graph.calls), 2)
            self.assertEqual(dry_result["vector"]["dry_run"], 2)
            self.assertEqual(dry_result["graph"]["dry_run"], 2)

        self.run_in_db(scenario)


if __name__ == "__main__":
    unittest.main()
