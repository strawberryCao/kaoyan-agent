import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from kaoyan_agent.agents.nightly_memory_agent import NightlyMemoryResult
from kaoyan_agent.core.settings import Settings
from kaoyan_agent.db import database
from kaoyan_agent.memory.embeddings import EmbeddingClient
from kaoyan_agent.memory.gates import MemoryGateEngine
from kaoyan_agent.schemas.nightly_memory import NightlyMemoryUpdateOutput
from kaoyan_agent.workflows.nightly_memory_workflow import NightlyMemoryWorkflow


class FakeHttpResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def redesigned_payload() -> dict:
    return {
        "daily_summary": "今天发现计划执行不稳定，但有一个可复用的小步启动流程。",
        "key_events": [
            {
                "event_type": "chat",
                "content": "用户反馈数学计划经常被打断。",
                "importance": 4,
                "subject": "数学",
                "source_event_ids": [],
            }
        ],
        "episodic_memories": [
            {
                "event_type": "planning_feedback",
                "content": "用户今天没有完成数学计划。",
                "subject": "数学",
                "occurred_at": "2026-06-06",
                "importance": 4,
                "source_event_ids": [],
                "evidence_refs": [],
            }
        ],
        "daily_memory_graph": {
            "nodes": [
                {
                    "node_id": "episode:1",
                    "node_type": "episode",
                    "title": "数学计划被打断",
                    "content": "用户今天没有完成数学计划。",
                    "ref_type": "",
                    "ref_id": None,
                    "metadata": {},
                }
            ],
            "edges": [],
            "summary": "计划执行问题需要进入门控。",
        },
        "discovered_problems": [
            {
                "operation": "insert",
                "problem_type": "planning_issue",
                "subject": "数学",
                "description": "数学计划执行稳定性不足。",
                "evidence": ["用户反馈数学计划经常被打断。"],
                "evidence_refs": [],
                "root_cause": "任务粒度过大。",
                "severity": 4,
                "confidence": 0.8,
                "value_score": 5,
                "suggested_action": "拆成 25 分钟任务块。",
                "status": "open",
                "merge_key": "math-plan-stability",
                "target_problem_id": None,
                "reason": "会影响后续学习安排。",
            }
        ],
        "memory_updates": [
            {
                "operation": "insert",
                "memory_type": "learning_status",
                "content": "用户数学计划执行稳定性偏弱。",
                "importance": 4,
                "confidence": 0.75,
                "merge_key": "math-plan-stability-memory",
                "reason": "后续计划生成需要降低任务粒度。",
                "status": "active",
                "valid_from": "2026-06-06",
                "subject": "数学",
                "evidence_refs": [{"source_type": "raw_event", "source_id": 1, "quote": "用户反馈数学计划经常被打断。", "note": ""}],
                "target_memory_id": None,
            }
        ],
        "skill_updates": [
            {
                "operation": "insert",
                "skill_name": "25分钟小步启动",
                "description": "当计划执行不稳定时，把任务拆成一个 25 分钟可启动块。",
                "trigger": {"problem_type": "planning_issue"},
                "procedure": {"steps": ["选一个最小题组", "设定25分钟", "结束后记录阻塞点"]},
                "confidence": 0.8,
                "effectiveness_score": 0.5,
                "status": "active",
                "evidence": ["用户反馈大任务难完成，小块任务更可执行。"],
                "evidence_refs": [],
                "merge_key": "skill-25min-start",
                "target_skill_id": None,
                "reason": "可复用干预流程。",
            }
        ],
        "next_actions": [
            {
                "action_type": "study_task",
                "content": "明天先完成一个 25 分钟数学小任务。",
                "related_problem": "数学计划执行稳定性不足。",
                "priority": 4,
            }
        ],
    }


class FakeSuccessAgent:
    def __init__(self, settings=None):
        self.settings = settings

    def run(self, **kwargs):
        output = NightlyMemoryUpdateOutput.model_validate(redesigned_payload())
        return NightlyMemoryResult(
            output=output,
            raw_response=json.dumps(output.model_dump(), ensure_ascii=False),
            parse_status="success",
        )


class FakeFailedAgent:
    def __init__(self, settings=None):
        self.settings = settings

    def run(self, **kwargs):
        output = NightlyMemoryUpdateOutput(
            daily_summary="结构化解析失败。",
            key_events=[],
            discovered_problems=[],
            memory_updates=[],
            skill_updates=[],
            next_actions=[
                {
                    "action_type": "follow_up",
                    "content": "检查模型 JSON 输出。",
                    "related_problem": "",
                    "priority": 3,
                }
            ],
        )
        return NightlyMemoryResult(
            output=output,
            raw_response="{bad json}",
            parse_status="failed",
            error_message="validation failed",
        )


class FakePartialAgent:
    def __init__(self, settings=None):
        self.settings = settings

    def run(self, **kwargs):
        payload = redesigned_payload()
        payload["discovered_problems"] = []
        payload["skill_updates"] = []
        output = NightlyMemoryUpdateOutput.model_validate(payload)
        candidate_results = [
            {
                "target_type": "problem",
                "candidate_index": 0,
                "operation": "skip",
                "target_id": None,
                "merge_key": "",
                "similarity": 0.0,
                "lexical_score": 0.0,
                "embedding_status": "not_called",
                "embedding_provider": "",
                "embedding_model": "",
                "reason": "evidence_missing",
                "error": "evidence_missing",
                "validation_status": "skipped",
                "skip_reason": "evidence_missing",
                "evidence_refs": [],
                "candidate": {"description": "no evidence", "evidence": []},
            },
            {
                "target_type": "skill",
                "candidate_index": 0,
                "operation": "skip",
                "target_id": None,
                "merge_key": "",
                "similarity": 0.0,
                "lexical_score": 0.0,
                "embedding_status": "not_called",
                "embedding_provider": "",
                "embedding_model": "",
                "reason": "not_reusable_skill",
                "error": "not_reusable_skill",
                "validation_status": "skipped",
                "skip_reason": "not_reusable_skill",
                "evidence_refs": [],
                "candidate": {"skill_name": "", "procedure": {}},
            },
        ]
        return NightlyMemoryResult(
            output=output,
            raw_response=json.dumps(payload, ensure_ascii=False),
            parse_status="partial_success",
            validation_errors=candidate_results,
            normalization_diagnostics=[
                {
                    "target_type": "graph_node",
                    "candidate_index": 0,
                    "source_field": "label",
                    "target_field": "title/content",
                    "action": "mapped",
                }
            ],
            candidate_results=candidate_results,
        )


class MemorySystemRedesignTest(unittest.TestCase):
    def test_embedding_client_uses_openai_compatible_api_shape(self):
        settings = Settings(
            "llm-key",
            None,
            "model",
            embedding_api_key="embedding-key",
            embedding_base_url="https://api.siliconflow.cn/v1",
            embedding_model="BAAI/bge-m3",
        )
        client = EmbeddingClient(settings)

        def fake_urlopen(http_request, timeout):
            self.assertEqual(timeout, 20.0)
            self.assertEqual(http_request.full_url, "https://api.siliconflow.cn/v1/embeddings")
            body = json.loads(http_request.data.decode("utf-8"))
            self.assertEqual(body["model"], "BAAI/bge-m3")
            self.assertEqual(body["input"], "数学计划")
            return FakeHttpResponse({"data": [{"embedding": [0.1, 0.2, 0.3]}]})

        with patch("kaoyan_agent.memory.embeddings.request.urlopen", fake_urlopen):
            vector = client.encode("数学计划")

        self.assertEqual(vector, [0.1, 0.2, 0.3])
        self.assertEqual(client.last_status, "success")

    def test_gate_falls_back_to_lexical_similarity_without_embedding_key(self):
        gate = MemoryGateEngine(
            embedding_client=EmbeddingClient(Settings("llm-key", None, "model"))
        )
        decision = gate.decide_memory(
            {
                "operation": "insert",
                "content": "用户数学计划执行稳定性偏弱",
                "memory_type": "learning_status",
                "confidence": 0.9,
                "evidence_refs": [{"source_type": "raw_event", "source_id": 1, "quote": "数学计划执行稳定性偏弱", "note": ""}],
            },
            [
                {
                    "id": 42,
                    "content": "用户数学计划执行稳定性偏弱",
                    "memory_type": "learning_status",
                    "embedding": [],
                }
            ],
        )

        self.assertEqual(decision.operation, "merge")
        self.assertEqual(decision.target_id, 42)
        self.assertEqual(decision.embedding_status, "disabled")
        record = decision.to_record("memory")
        self.assertEqual(record["embedding_provider"], "siliconflow")
        self.assertEqual(record["embedding_model"], "BAAI/bge-m3")
        self.assertEqual(record["error"], "EMBEDDING_API_KEY is missing")

    def test_skill_gate_skips_one_off_advice_without_reusable_procedure(self):
        gate = MemoryGateEngine(
            embedding_client=EmbeddingClient(Settings("llm-key", None, "model"))
        )
        decision = gate.decide_skill(
            {
                "operation": "insert",
                "skill_name": "one-time reminder",
                "description": "Tell the user to sleep early tonight.",
                "trigger": {"date": "today"},
                "procedure": {},
                "confidence": 0.95,
            },
            [],
        )

        self.assertEqual(decision.operation, "skip")
        self.assertIn("procedure", decision.reason)

    def test_successful_nightly_flow_writes_memory_problem_skill_and_gates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                with patch(
                    "kaoyan_agent.workflows.nightly_memory_workflow.NightlyMemoryAgent",
                    FakeSuccessAgent,
                ):
                    result = NightlyMemoryWorkflow(settings=settings).run("2026-06-06")

                self.assertEqual(result.parse_status, "success")
                self.assertEqual(len(result.inserted_memory_ids), 2)
                self.assertEqual(len(result.inserted_problem_ids), 1)
                self.assertEqual(len(result.inserted_skill_ids), 1)
                self.assertEqual(len(result.gate_results), 3)
                self.assertTrue(result.daily_memory_graph_id)

                with closing(sqlite3.connect(db_path)) as connection:
                    memory_count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                    problem_count = connection.execute("SELECT COUNT(*) FROM problem_board").fetchone()[0]
                    skill_count = connection.execute("SELECT COUNT(*) FROM skill_memories").fetchone()[0]
                    gate_json = connection.execute(
                        "SELECT gate_results_json, inserted_counts_json, index_sync_status_json FROM nightly_reviews"
                    ).fetchone()[0]
                    global_nodes = connection.execute(
                        "SELECT COUNT(*) FROM global_graph_nodes"
                    ).fetchone()[0]
                    daily_nodes = connection.execute("SELECT COUNT(*) FROM daily_graph_nodes").fetchone()[0]
                    daily_edges = connection.execute("SELECT COUNT(*) FROM daily_graph_edges").fetchone()[0]
                    memory_types = {
                        row[0]
                        for row in connection.execute("SELECT memory_type FROM memories").fetchall()
                    }

                self.assertEqual(memory_count, 2)
                self.assertEqual(problem_count, 1)
                self.assertEqual(skill_count, 1)
                with closing(sqlite3.connect(db_path)) as connection:
                    review = connection.execute(
                        "SELECT gate_results_json, inserted_counts_json, index_sync_status_json FROM nightly_reviews"
                    ).fetchone()
                gate_records = json.loads(review[0])
                inserted_counts = json.loads(review[1])
                index_sync_status = json.loads(review[2])
                self.assertEqual(len(gate_records), 3)
                for gate_record in gate_records:
                    self.assertIn(gate_record["operation"], {"insert", "update", "merge", "skip"})
                    self.assertIn("embedding_status", gate_record)
                    self.assertIn("embedding_provider", gate_record)
                    self.assertIn("embedding_model", gate_record)
                    self.assertIn("lexical_score", gate_record)
                    self.assertIn("validation_status", gate_record)
                    self.assertIn("skip_reason", gate_record)
                    self.assertIn("error", gate_record)
                self.assertIn("episodic", memory_types)
                self.assertIn("learning_status", memory_types)
                self.assertEqual(inserted_counts["episodic_memories"], 1)
                self.assertEqual(inserted_counts["legacy_memory_updates"], 1)
                self.assertIn("vector", index_sync_status)
                self.assertIn("graph", index_sync_status)
                self.assertGreater(daily_nodes, 0)
                self.assertGreaterEqual(daily_edges, 0)
                self.assertGreaterEqual(global_nodes, 4)

    def test_partial_success_only_records_review_diagnostics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                with patch(
                    "kaoyan_agent.workflows.nightly_memory_workflow.NightlyMemoryAgent",
                    FakePartialAgent,
                ):
                    result = NightlyMemoryWorkflow(settings=settings).run("2026-06-06")

                self.assertEqual(result.parse_status, "partial_success")
                self.assertEqual(result.inserted_memory_ids, [])
                self.assertEqual(result.inserted_problem_ids, [])
                self.assertEqual(result.inserted_skill_ids, [])
                self.assertIsNone(result.daily_memory_graph_id)
                self.assertEqual(result.gate_results, [])

                with closing(sqlite3.connect(db_path)) as connection:
                    connection.row_factory = sqlite3.Row
                    review = connection.execute(
                        """
                        SELECT parse_status, candidate_results_json,
                               normalization_diagnostics_json, gate_results_json,
                               inserted_counts_json, index_sync_status_json
                        FROM nightly_reviews
                        """
                    ).fetchone()
                    problem_ops = connection.execute("SELECT COUNT(*) FROM problem_operations").fetchone()[0]
                    skill_ops = connection.execute("SELECT COUNT(*) FROM skill_operations").fetchone()[0]
                    memory_count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                    graph_count = connection.execute("SELECT COUNT(*) FROM daily_memory_graphs").fetchone()[0]

                self.assertEqual(review["parse_status"], "partial_success")
                self.assertEqual(len(json.loads(review["candidate_results_json"])), 2)
                self.assertEqual(len(json.loads(review["normalization_diagnostics_json"])), 1)
                self.assertEqual(json.loads(review["gate_results_json"]), [])
                self.assertEqual(problem_ops, 0)
                self.assertEqual(skill_ops, 0)
                self.assertEqual(memory_count, 0)
                self.assertEqual(graph_count, 0)
                self.assertEqual(json.loads(review["inserted_counts_json"])["episodic_memories"], 0)
                self.assertEqual(json.loads(review["index_sync_status_json"])["vector"]["status"], "skipped")

    def test_init_db_adds_nightly_diagnostics_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                with closing(sqlite3.connect(db_path)) as connection:
                    columns = {
                        row[1]
                        for row in connection.execute("PRAGMA table_info(nightly_reviews)").fetchall()
                    }

        self.assertIn("validation_errors_json", columns)
        self.assertIn("normalization_diagnostics_json", columns)
        self.assertIn("candidate_results_json", columns)
        self.assertIn("index_sync_status_json", columns)
        self.assertIn("inserted_counts_json", columns)

    def test_duplicate_memory_problem_and_skill_merge_instead_of_insert(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                with patch(
                    "kaoyan_agent.workflows.nightly_memory_workflow.NightlyMemoryAgent",
                    FakeSuccessAgent,
                ):
                    first = NightlyMemoryWorkflow(settings=settings).run("2026-06-06")
                    second = NightlyMemoryWorkflow(settings=settings).run("2026-06-07")

                self.assertEqual(len(first.inserted_memory_ids), 2)
                self.assertEqual(len(first.inserted_problem_ids), 1)
                self.assertEqual(len(first.inserted_skill_ids), 1)
                self.assertEqual(second.inserted_memory_ids, [])
                self.assertEqual(second.inserted_problem_ids, [])
                self.assertEqual(second.inserted_skill_ids, [])
                self.assertEqual(
                    [item["operation"] for item in second.gate_results],
                    ["merge", "merge", "merge"],
                )

                with closing(sqlite3.connect(db_path)) as connection:
                    memory_count = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
                    problem_count = connection.execute("SELECT COUNT(*) FROM problem_board").fetchone()[0]
                    skill_count = connection.execute("SELECT COUNT(*) FROM skill_memories").fetchone()[0]
                    memory_ops = connection.execute("SELECT COUNT(*) FROM memory_operations").fetchone()[0]
                    problem_ops = connection.execute("SELECT COUNT(*) FROM problem_operations").fetchone()[0]
                    skill_ops = connection.execute("SELECT COUNT(*) FROM skill_operations").fetchone()[0]
                    global_nodes = connection.execute("SELECT COUNT(*) FROM global_graph_nodes").fetchone()[0]

                self.assertEqual(memory_count, 2)
                self.assertEqual(problem_count, 1)
                self.assertEqual(skill_count, 1)
                self.assertEqual(memory_ops, 4)
                self.assertEqual(problem_ops, 2)
                self.assertEqual(skill_ops, 2)
                self.assertGreaterEqual(global_nodes, 4)

    def test_failed_nightly_parse_does_not_write_long_term_tables(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "app.db"
            settings = Settings("", None, "test-model", database_path=db_path)
            with patch.object(database, "get_settings", return_value=settings):
                database.init_db()
                with patch(
                    "kaoyan_agent.workflows.nightly_memory_workflow.NightlyMemoryAgent",
                    FakeFailedAgent,
                ):
                    result = NightlyMemoryWorkflow(settings=settings).run("2026-06-06")

                self.assertEqual(result.parse_status, "failed")
                self.assertEqual(result.inserted_memory_ids, [])
                self.assertEqual(result.inserted_problem_ids, [])
                self.assertEqual(result.inserted_skill_ids, [])
                self.assertIsNone(result.daily_memory_graph_id)

                with closing(sqlite3.connect(db_path)) as connection:
                    counts = {
                        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                        for table in [
                            "memories",
                            "problem_board",
                            "skill_memories",
                            "daily_memory_graphs",
                        ]
                    }
                    parse_status = connection.execute(
                        "SELECT parse_status FROM nightly_reviews"
                    ).fetchone()[0]

                self.assertEqual(counts, {key: 0 for key in counts})
                self.assertEqual(parse_status, "failed")


if __name__ == "__main__":
    unittest.main()
