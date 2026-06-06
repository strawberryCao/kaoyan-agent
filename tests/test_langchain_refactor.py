import builtins
import json
import types
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from kaoyan_agent.agents.chat_agent import ChatAgent
from kaoyan_agent.agents.chat_tools import build_readonly_chat_tools
from kaoyan_agent.agents.motivation import MotivationAgent
from kaoyan_agent.agents.nightly_memory_agent import NightlyMemoryAgent
from kaoyan_agent.agents.practice_review import PracticeReviewAgent
from kaoyan_agent.core.settings import Settings
from kaoyan_agent.schemas.contracts import AgentRequest
from kaoyan_agent.schemas.motivation import (
    DailySignOutput,
    RandomTaskOutput,
    SoothingTaskOutput,
)
from kaoyan_agent.schemas.nightly_memory import NightlyMemoryUpdateOutput
from kaoyan_agent.schemas.practice_review import PracticeReviewCard
from kaoyan_agent.services.llm_client import LLMConfigError, create_langchain_model


def module_not_found(name: str) -> ModuleNotFoundError:
    return ModuleNotFoundError(f"No module named '{name}'", name=name)


def valid_nightly_payload() -> dict:
    return {
        "daily_summary": "ok",
        "key_events": [
            {"event_type": "chat", "content": "finished one review", "importance": 3}
        ],
        "discovered_problems": [],
        "memory_updates": [],
        "next_actions": [
            {
                "action_type": "follow_up",
                "content": "check tomorrow",
                "related_problem": "",
                "priority": 3,
            }
        ],
    }


class FakeLangChainAgent:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response or {}
        self.error = error

    def invoke(self, request):
        if self.error:
            raise self.error
        self.request = request
        return self.response


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class FakeLLMClientForChat:
    def __init__(self):
        self.settings = Settings("key", None, "model")


def invoke_tool(tool_item, **kwargs):
    if hasattr(tool_item, "invoke"):
        return tool_item.invoke(kwargs)
    return tool_item(**kwargs)


def tool_name(tool_item) -> str:
    return getattr(tool_item, "name", "") or getattr(tool_item, "__name__", "")


class LLMClientFactoryTest(unittest.TestCase):
    def test_create_langchain_model_requires_api_key(self):
        with self.assertRaisesRegex(LLMConfigError, "LLM_API_KEY"):
            create_langchain_model(Settings("", None, "model"))

    def test_create_langchain_model_prefers_deepseek(self):
        calls = []

        class FakeChatDeepSeek:
            def __init__(self, **kwargs):
                calls.append(("deepseek", kwargs))

        class FakeChatOpenAI:
            def __init__(self, **kwargs):
                calls.append(("openai", kwargs))

        deepseek_module = types.ModuleType("langchain_deepseek")
        deepseek_module.ChatDeepSeek = FakeChatDeepSeek
        openai_module = types.ModuleType("langchain_openai")
        openai_module.ChatOpenAI = FakeChatOpenAI

        with patch.dict(
            "sys.modules",
            {
                "langchain_deepseek": deepseek_module,
                "langchain_openai": openai_module,
            },
        ):
            model = create_langchain_model(
                Settings("key", "https://api.example.test", "deepseek-chat"),
                temperature=0.1,
            )

        self.assertIsInstance(model, FakeChatDeepSeek)
        self.assertEqual(calls[0][0], "deepseek")
        self.assertEqual(calls[0][1]["model"], "deepseek-chat")
        self.assertEqual(calls[0][1]["base_url"], "https://api.example.test")
        self.assertEqual(len(calls), 1)

    def test_create_langchain_model_falls_back_to_openai_provider(self):
        calls = []
        real_import = builtins.__import__

        class FakeChatOpenAI:
            def __init__(self, **kwargs):
                calls.append(kwargs)

        openai_module = types.ModuleType("langchain_openai")
        openai_module.ChatOpenAI = FakeChatOpenAI

        def fake_import(name, *args, **kwargs):
            if name == "langchain_deepseek":
                raise module_not_found("langchain_deepseek")
            if name == "langchain_openai":
                return openai_module
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            model = create_langchain_model(Settings("key", None, "gpt-4o-mini"))

        self.assertIsInstance(model, FakeChatOpenAI)
        self.assertEqual(calls[0]["model"], "gpt-4o-mini")

    def test_create_langchain_model_reports_missing_providers(self):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name in {"langchain_deepseek", "langchain_openai"}:
                raise module_not_found(name)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaisesRegex(LLMConfigError, "No LangChain chat model"):
                create_langchain_model(Settings("key", None, "model"))


class NightlyMemoryLangChainTest(unittest.TestCase):
    def test_nightly_memory_uses_structured_response(self):
        payload = valid_nightly_payload()

        def fake_create_agent(**kwargs):
            self.assertIs(kwargs["response_format"], NightlyMemoryUpdateOutput)
            return FakeLangChainAgent({"structured_response": payload})

        with patch(
            "kaoyan_agent.services.llm_client.create_langchain_model",
            return_value=object(),
        ), patch(
            "kaoyan_agent.services.llm_client.create_agent",
            side_effect=fake_create_agent,
        ):
            result = NightlyMemoryAgent(Settings("key", None, "model")).run(
                review_date="2026-06-06",
                conversations=[],
            )

        self.assertEqual(result.parse_status, "success")
        self.assertEqual(result.output.daily_summary, "ok")
        self.assertIn("daily_summary", result.raw_response)

    def test_nightly_memory_missing_structured_response_fails(self):
        with patch(
            "kaoyan_agent.services.llm_client.create_langchain_model",
            return_value=object(),
        ), patch(
            "kaoyan_agent.services.llm_client.create_agent",
            return_value=FakeLangChainAgent({"messages": []}),
        ):
            result = NightlyMemoryAgent(Settings("key", None, "model")).run(
                review_date="2026-06-06",
                conversations=[],
            )

        self.assertEqual(result.parse_status, "failed")
        self.assertIn("structured_response", result.error_message)

    def test_nightly_memory_invalid_structured_response_fails(self):
        payload = valid_nightly_payload()
        payload["next_actions"][0]["priority"] = 9

        with patch(
            "kaoyan_agent.services.llm_client.create_langchain_model",
            return_value=object(),
        ), patch(
            "kaoyan_agent.services.llm_client.create_agent",
            return_value=FakeLangChainAgent({"structured_response": payload}),
        ):
            result = NightlyMemoryAgent(Settings("key", None, "model")).run(
                review_date="2026-06-06",
                conversations=[],
            )

        self.assertEqual(result.parse_status, "failed")
        self.assertFalse(hasattr(NightlyMemoryAgent, "run_raw_json_fallback"))
        self.assertFalse(hasattr(NightlyMemoryAgent, "validate_response"))


class PracticeReviewLangChainTest(unittest.TestCase):
    def test_practice_review_card_schema_validates(self):
        card = PracticeReviewCard.model_validate(
            {
                "knowledge_points": ["limit", "condition"],
                "mistake_reason": "concept_gap",
                "analysis": "Need to check conditions first.",
                "review_priority": 4,
            }
        )
        self.assertEqual(card.mistake_reason, "concept_gap")

        with self.assertRaises(ValidationError):
            PracticeReviewCard.model_validate(
                {
                    "knowledge_points": "limit",
                    "mistake_reason": "bad_reason",
                    "analysis": "x",
                    "review_priority": 4,
                }
            )
        with self.assertRaises(ValidationError):
            PracticeReviewCard.model_validate(
                {
                    "knowledge_points": "limit",
                    "mistake_reason": "concept_gap",
                    "analysis": "x",
                    "review_priority": 6,
                }
            )

    def test_practice_review_uses_langchain_card_then_normalizes(self):
        def fake_create_agent(**kwargs):
            self.assertIs(kwargs["response_format"], PracticeReviewCard)
            return FakeLangChainAgent(
                {
                    "structured_response": {
                        "knowledge_points": ["limit", "conditions"],
                        "mistake_reason": "method_gap",
                        "analysis": "Check method conditions before applying.",
                        "review_priority": 5,
                    }
                }
            )

        with patch(
            "kaoyan_agent.services.llm_client.create_langchain_model",
            return_value=object(),
        ), patch(
            "kaoyan_agent.services.llm_client.create_agent",
            side_effect=fake_create_agent,
        ):
            card = PracticeReviewAgent(Settings("key", None, "model")).generate_card(
                subject="math",
                chapter="limit",
                question="forgot L'Hopital condition",
                user_reason="method",
            )

        self.assertEqual(card["knowledge_points"], "limit; conditions")
        self.assertEqual(card["mistake_reason"], "method_gap")
        self.assertEqual(card["review_priority"], 5)

    def test_practice_review_uses_local_fallback_on_langchain_failure(self):
        with patch(
            "kaoyan_agent.services.llm_client.create_langchain_model",
            side_effect=RuntimeError("structured down"),
        ):
            card = PracticeReviewAgent(Settings("key", None, "model")).generate_card(
                subject="math",
                chapter="limit",
                question="forgot condition",
                user_reason="concept",
            )

        self.assertIn("generation_error", card)
        self.assertEqual(card["mistake_reason"], "concept_gap")
        self.assertFalse(hasattr(__import__("kaoyan_agent.agents.practice_review"), "safe_generate_with_llm"))


class ChatAgentLangChainTest(unittest.TestCase):
    def build_request(self) -> AgentRequest:
        return AgentRequest(
            request_id="req-1",
            user_id="default",
            session_id=1,
            input_text="what should I review today?",
            context={
                "messages": [{"role": "user", "content": "what should I review today?"}],
                "system_prompt": "You are ChatAgent.",
            },
            metadata={"project_id": None},
        )

    def test_chat_agent_uses_create_agent_tools(self):
        captured = {}

        def fake_create_agent(**kwargs):
            captured.update(kwargs)
            return FakeLangChainAgent(
                {"messages": [FakeMessage("langchain tool answer")]}
            )

        with patch(
            "kaoyan_agent.services.llm_client.create_langchain_model",
            return_value=object(),
        ), patch(
            "kaoyan_agent.agents.chat_agent.build_readonly_chat_tools",
            return_value=[lambda: "tool", lambda: "tool2", lambda: "tool3"],
        ), patch(
            "kaoyan_agent.services.llm_client.create_agent",
            side_effect=fake_create_agent,
        ):
            response = ChatAgent(FakeLLMClientForChat()).run(self.build_request())

        self.assertEqual(response.text, "langchain tool answer")
        self.assertEqual(response.parse_status, "ok")
        self.assertTrue(response.structured_data["langchain_agent"])
        self.assertEqual(len(captured["tools"]), 3)

    def test_chat_agent_langchain_failure_returns_error(self):
        with patch(
            "kaoyan_agent.services.llm_client.create_langchain_model",
            side_effect=RuntimeError("langchain down"),
        ):
            response = ChatAgent(FakeLLMClientForChat()).run(self.build_request())

        self.assertEqual(response.parse_status, "llm_request_error")
        self.assertIn("langchain down", response.errors[0])

    def test_chat_tools_are_read_only_and_documented(self):
        class FakeProblemRepository:
            def list_open(self, project_id=None):
                return [
                    {
                        "id": 1,
                        "problem_type": "planning_issue",
                        "subject": "math",
                        "description": "task too large",
                        "severity": 4,
                        "value_score": 5,
                        "suggested_action": "split task",
                        "status": "open",
                    }
                ]

        class FakeStudyTaskRepository:
            def list(self, date_str=None, limit=None, project_id=None):
                return [
                    {
                        "id": 2,
                        "title": "review limit",
                        "subject": "math",
                        "status": "todo",
                        "estimated_minutes": 25,
                        "source": "Problem Board",
                        "related_problem_id": 1,
                    }
                ]

        class FakeMemoryRetriever:
            def retrieve(self, query, decision, limit=5, project_id=None):
                return []

        with patch(
            "kaoyan_agent.agents.chat_tools.ProblemRepository",
            FakeProblemRepository,
        ), patch(
            "kaoyan_agent.agents.chat_tools.StudyTaskRepository",
            FakeStudyTaskRepository,
        ), patch(
            "kaoyan_agent.agents.chat_tools.MemoryRetriever",
            FakeMemoryRetriever,
        ):
            tools = build_readonly_chat_tools(project_id=None)

        names = {tool_name(tool_item) for tool_item in tools}
        self.assertEqual(
            names,
            {
                "list_open_problems_tool",
                "list_today_tasks_tool",
                "search_memory_tool",
            },
        )
        for tool_item in tools:
            description = getattr(tool_item, "description", "") or getattr(
                tool_item, "__doc__", ""
            )
            self.assertTrue(description.strip())

        problems = json.loads(invoke_tool(tools[0], limit=5))
        tasks = json.loads(invoke_tool(tools[1], limit=5))
        memories = json.loads(invoke_tool(tools[2], query="math", limit=5))

        self.assertEqual(problems[0]["description"], "task too large")
        self.assertEqual(tasks[0]["title"], "review limit")
        self.assertEqual(memories, [])


class MotivationLangChainTest(unittest.TestCase):
    def test_motivation_structured_outputs(self):
        outputs = [
            {
                "structured_response": {
                    "sign_level": "good",
                    "sign_text": "Keep pace.",
                    "today_advice": "Do one task.",
                    "action": "Start with math.",
                }
            },
            {
                "structured_response": {
                    "title": "Review one card",
                    "subject": "math",
                    "estimated_minutes": 10,
                    "reason": "Small progress.",
                }
            },
            {
                "structured_response": {
                    "title": "Read one mistake reason",
                    "subject": "low-energy start",
                    "estimated_minutes": 3,
                    "reason": "Keep the action small.",
                }
            },
        ]

        def fake_create_agent(**kwargs):
            self.assertIn(
                kwargs["response_format"],
                {DailySignOutput, RandomTaskOutput, SoothingTaskOutput},
            )
            return FakeLangChainAgent(outputs.pop(0))

        with patch(
            "kaoyan_agent.services.llm_client.create_langchain_model",
            return_value=object(),
        ), patch(
            "kaoyan_agent.services.llm_client.create_agent",
            side_effect=fake_create_agent,
        ):
            agent = MotivationAgent(Settings("key", None, "model"))
            sign = agent.generate_daily_sign()
            task = agent.generate_random_task()
            soothing = agent.generate_soothing_task("tired")

        self.assertEqual(sign["sign_level"], "good")
        self.assertEqual(task["title"], "Review one card")
        self.assertEqual(soothing["estimated_minutes"], 3)

    def test_motivation_uses_local_fallback_on_failure(self):
        with patch(
            "kaoyan_agent.services.llm_client.create_langchain_model",
            side_effect=RuntimeError("structured down"),
        ):
            agent = MotivationAgent(Settings("key", None, "model"))
            sign = agent.generate_daily_sign()
            task = agent.generate_random_task()
            soothing = agent.generate_soothing_task("tired")

        self.assertIn("generation_error", sign)
        self.assertIn("generation_error", task)
        self.assertIn("generation_error", soothing)


if __name__ == "__main__":
    unittest.main()
