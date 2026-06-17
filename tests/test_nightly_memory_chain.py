import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from kaoyan_agent.agents.nightly_memory_agent import NightlyMemoryResult
from kaoyan_agent.agents.problem_discovery_agent import ProblemDiscoveryResult
from kaoyan_agent.core.settings import Settings
from kaoyan_agent.db import database
from kaoyan_agent.schemas.nightly_memory import NightlyMemoryExtraction, NightlyMemoryUpdateOutput
from kaoyan_agent.workflows.nightly_memory_workflow import NightlyMemoryWorkflow


def formal_payload() -> dict:
    return {
        "daily_summary": "today has planning evidence and a stable math weakness",
        "episodic_memories": [
            {
                "title": "planning interruption",
                "content": "The student reported the math plan was interrupted.",
                "event_date": "2026-06-06",
                "evidence_event_ids": [1],
                "confidence": 0.8,
            }
        ],
        "semantic_memories": [
            {
                "title": "math planning weakness",
                "content": "Math planning needs smaller executable blocks.",
                "category": "planning",
                "evidence_event_ids": [1],
                "confidence": 0.82,
            }
        ],
        "daily_graph_nodes": [
            {
                "node_key": "raw_event:1",
                "node_type": "raw_event",
                "title": "raw evidence",
                "content": "math plan interrupted",
                "ref_type": "raw_event",
                "ref_id": 1,
                "confidence": 1.0,
            },
            {
                "node_key": "semantic:planning",
                "node_type": "semantic_memory",
                "title": "planning weakness",
                "content": "needs smaller blocks",
                "confidence": 0.8,
            },
        ],
        "daily_graph_edges": [
            {
                "source_node_key": "raw_event:1",
                "target_node_key": "semantic:planning",
                "relation_type": "EVIDENCE_OF",
                "weight": 1.0,
                "evidence_event_ids": [1],
            }
        ],
        "candidate_problems": [
            {
                "operation": "insert",
                "problem_type": "planning_issue",
                "subject": "math",
                "description": "Math plan execution is unstable.",
                "evidence": ["math plan interrupted"],
                "root_cause": "tasks are too large",
                "severity": 4,
                "confidence": 0.8,
                "value_score": 5,
                "suggested_action": "split into 25-minute blocks",
                "status": "open",
                "merge_key": "problem:math-plan-unstable",
            }
        ],
        "next_actions": [
            {
                "action_type": "study_task",
                "content": "Create a 25-minute math block tomorrow.",
                "related_problem": "Math plan execution is unstable.",
                "priority": 4,
            }
        ],
    }


class FakeFormalAgent:
    def __init__(self, settings=None):
        self.settings = settings

    def run(self, **kwargs):
        output = NightlyMemoryUpdateOutput.model_validate(formal_payload())
        return NightlyMemoryResult(
            output=output,
            raw_response=json.dumps(output.model_dump(), ensure_ascii=False),
            parse_status="success",
        )


class FakeVectorStore:
    def __init__(self):
        self.problem_upserts = []

    def get_status(self):
        return {"available": True, "backend": "chroma"}

    def query(self, text, limit=8, project_id=None):
        return [
            {
                "source_type": "memory",
                "source_id": 1,
                "vector_similarity": 0.9,
                "metadata": {"retrieval_backend": "chroma_hybrid"},
            }
        ]

    def upsert_problem(self, problem, metadata=None):
        self.problem_upserts.append({"problem": problem, "metadata": metadata or {}})
        return {"status": "success", "id": f"problem:{problem.get('id')}"}


class FakeIndexService:
    def __init__(self):
        self.vector_store = FakeVectorStore()
        self.memory_sync_calls = []
        self.graph_sync_calls = []

    def sync_nightly_memories_to_chroma(self, memories, *, review_id, review_date):
        self.memory_sync_calls.append(
            {"memories": memories, "review_id": review_id, "review_date": review_date}
        )
        return {
            "backend": "chroma",
            "status": "success",
            "attempted": len(memories),
            "upserted": len(memories),
            "skipped": 0,
            "errors": [],
            "results": [{"status": "success"} for _ in memories],
        }

    def sync_daily_graph_to_neo4j(self, **kwargs):
        self.graph_sync_calls.append(kwargs)
        return {
            "backend": "neo4j",
            "status": "success",
            "attempted": 1,
            "upserted": 1,
            "skipped": 0,
            "errors": [],
            "results": [{"status": "success"}],
            "nodes_upserted": 1,
            "edges_upserted": 1,
        }


class FakeGraphProblemDiscovery:
    def __init__(self):
        self.calls = []

    def discover_from_graph(self, **kwargs):
        self.calls.append(kwargs)
        return ProblemDiscoveryResult(
            problems=list(kwargs.get("candidate_problems") or []),
            parse_status="success",
        )


class NightlyMemoryFormalChainTest(unittest.TestCase):
    def test_formal_extraction_schema_accepts_semantic_and_daily_graph(self):
        output = NightlyMemoryExtraction.model_validate(formal_payload())

        self.assertEqual(output.semantic_memories[0].category, "planning")
        self.assertEqual(output.daily_graph_nodes[1].node_type, "semantic_memory")
        self.assertEqual(output.daily_graph_edges[0].relation_type, "EVIDENCE_OF")
        self.assertEqual(output.candidate_problems[0].merge_key, "problem:math-plan-unstable")

    def test_successful_nightly_chain_persists_and_syncs_indexes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            fake_index = FakeIndexService()
            fake_discovery = FakeGraphProblemDiscovery()

            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                with closing(sqlite3.connect(db_path)) as connection:
                    connection.execute(
                        """
                        INSERT INTO raw_events (
                            project_id, session_id, role, content, source_type,
                            source_id, metadata_json, created_at
                        )
                        VALUES (NULL, NULL, 'user', 'math plan interrupted',
                                'chat_message', 1, '{}', '2026-06-06T01:00:00+00:00')
                        """
                    )
                    connection.commit()

                with patch(
                    "kaoyan_agent.workflows.nightly_memory_workflow.NightlyMemoryAgent",
                    FakeFormalAgent,
                ):
                    result = NightlyMemoryWorkflow(
                        settings=settings,
                        memory_index_service=fake_index,
                        problem_discovery_agent=fake_discovery,
                    ).run("2026-06-06")

                self.assertEqual(result.parse_status, "success")
                self.assertEqual(len(result.inserted_memory_ids), 2)
                self.assertEqual(len(result.inserted_problem_ids), 1)
                self.assertTrue(result.daily_memory_graph_id)

                with closing(sqlite3.connect(db_path)) as connection:
                    connection.row_factory = sqlite3.Row
                    memory_types = {
                        row["memory_type"]
                        for row in connection.execute("SELECT memory_type FROM memories")
                    }
                    daily_nodes = connection.execute("SELECT COUNT(*) FROM daily_graph_nodes").fetchone()[0]
                    daily_edges = connection.execute("SELECT COUNT(*) FROM daily_graph_edges").fetchone()[0]
                    global_nodes = connection.execute("SELECT COUNT(*) FROM global_graph_nodes").fetchone()[0]
                    review = connection.execute(
                        "SELECT inserted_counts_json, index_sync_status_json FROM nightly_reviews"
                    ).fetchone()

                inserted_counts = json.loads(review["inserted_counts_json"])
                index_status = json.loads(review["index_sync_status_json"])

                self.assertEqual(memory_types, {"episodic", "semantic"})
                self.assertGreaterEqual(daily_nodes, 2)
                self.assertGreaterEqual(daily_edges, 1)
                self.assertGreaterEqual(global_nodes, 2)
                self.assertEqual(inserted_counts["episodic_memories"], 1)
                self.assertEqual(inserted_counts["semantic_memories"], 1)
                self.assertEqual(index_status["vector"]["status"], "success")
                self.assertEqual(index_status["graph"]["status"], "success")
                self.assertEqual(len(fake_index.memory_sync_calls), 1)
                synced_memories = fake_index.memory_sync_calls[0]["memories"]
                self.assertEqual({item["memory_type"] for item in synced_memories}, {"episodic", "semantic"})
                self.assertEqual(len(fake_index.graph_sync_calls), 1)
                self.assertTrue(fake_discovery.calls)
                self.assertIn("daily_graph", fake_discovery.calls[0])
                self.assertEqual(fake_discovery.calls[0]["chroma_results"][0]["vector_similarity"], 0.9)


if __name__ == "__main__":
    unittest.main()
