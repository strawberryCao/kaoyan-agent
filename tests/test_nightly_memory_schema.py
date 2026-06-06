import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from kaoyan_agent.agents.nightly_memory_agent import NightlyMemoryResult
from kaoyan_agent.core.settings import Settings
from kaoyan_agent.db import database
from kaoyan_agent.schemas.nightly_memory import NightlyMemoryUpdateOutput
from kaoyan_agent.workflows.nightly_memory_workflow import NightlyMemoryWorkflow


def valid_payload() -> dict:
    return {
        "daily_summary": "今天完成了结构化复盘。",
        "key_events": [
            {"event_type": "chat", "content": "用户反馈数学计划执行不稳。", "importance": 4}
        ],
        "discovered_problems": [
            {
                "problem_type": "planning_issue",
                "subject": "数学",
                "description": "复习计划经常被打断。",
                "evidence": ["用户说今天又没按计划做完数学。"],
                "root_cause": "任务粒度过大。",
                "severity": 4,
                "confidence": 0.8,
                "value_score": 5,
                "suggested_action": "把数学任务拆成 25 分钟块。",
                "status": "open",
            }
        ],
        "memory_updates": [
            {
                "operation": "insert",
                "memory_type": "learning_status",
                "content": "用户数学计划执行稳定性较弱。",
                "importance": 4,
                "confidence": 0.75,
                "merge_key": "math-planning-stability",
                "reason": "会影响后续计划建议。",
            }
        ],
        "next_actions": [
            {
                "action_type": "study_task",
                "content": "明天先完成一个 25 分钟数学小任务。",
                "related_problem": "复习计划经常被打断。",
                "priority": 4,
            }
        ],
    }


class FakeSuccessAgent:
    def __init__(self, settings=None):
        self.settings = settings

    def run(self, **kwargs):
        output = NightlyMemoryUpdateOutput.model_validate(valid_payload())
        return NightlyMemoryResult(
            output=output,
            raw_response=json.dumps(valid_payload(), ensure_ascii=False),
            parse_status="success",
        )


class FakeFailedAgent:
    def __init__(self, settings=None):
        self.settings = settings

    def run(self, **kwargs):
        output = NightlyMemoryUpdateOutput(
            daily_summary="本次结构化解析失败。",
            key_events=[],
            discovered_problems=[],
            memory_updates=[],
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
            raw_response="{not json}",
            parse_status="failed",
            error_message="validation failed",
        )


class NightlyMemorySchemaTest(unittest.TestCase):
    def test_valid_json_passes_model_validate_json(self):
        raw_json = json.dumps(valid_payload(), ensure_ascii=False)
        output = NightlyMemoryUpdateOutput.model_validate_json(raw_json)
        self.assertEqual(output.discovered_problems[0].problem_type, "planning_issue")

    def test_invalid_enum_raises_validation_error(self):
        payload = valid_payload()
        payload["discovered_problems"][0]["problem_type"] = "bad_type"
        with self.assertRaises(ValidationError):
            NightlyMemoryUpdateOutput.model_validate_json(
                json.dumps(payload, ensure_ascii=False)
            )

    def test_failed_parse_does_not_write_problem_or_memory(self):
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
                self.assertEqual(result.inserted_problem_ids, [])
                self.assertEqual(result.inserted_memory_ids, [])
                with closing(sqlite3.connect(db_path)) as connection:
                    problem_count = connection.execute(
                        "SELECT COUNT(*) FROM problem_board"
                    ).fetchone()[0]
                    memory_count = connection.execute(
                        "SELECT COUNT(*) FROM memories"
                    ).fetchone()[0]
                    parse_status = connection.execute(
                        "SELECT parse_status FROM nightly_reviews"
                    ).fetchone()[0]
                self.assertEqual(problem_count, 0)
                self.assertEqual(memory_count, 0)
                self.assertEqual(parse_status, "failed")

    def test_successful_parse_writes_problem_and_memory(self):
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
                self.assertEqual(len(result.inserted_problem_ids), 1)
                self.assertEqual(len(result.inserted_memory_ids), 1)
                with closing(sqlite3.connect(db_path)) as connection:
                    problem_count = connection.execute(
                        "SELECT COUNT(*) FROM problem_board"
                    ).fetchone()[0]
                    memory_count = connection.execute(
                        "SELECT COUNT(*) FROM memories"
                    ).fetchone()[0]
                self.assertEqual(problem_count, 1)
                self.assertEqual(memory_count, 1)


if __name__ == "__main__":
    unittest.main()
