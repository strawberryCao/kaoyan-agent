import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.prompts.prompt_registry import PromptRegistry
from kaoyan_agent.schemas.nightly_memory import NightlyMemoryUpdateOutput
from kaoyan_agent.services.llm_client import LLMConfigError, run_structured_agent


@dataclass
class NightlyMemoryResult:
    output: NightlyMemoryUpdateOutput
    raw_response: str
    parse_status: str
    error_message: str = ""


class NightlyMemoryAgent:
    """Generate and validate nightly memory update output."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        prompt_registry: Optional[PromptRegistry] = None,
    ):
        self.settings = settings
        self.prompt_registry = prompt_registry or PromptRegistry()

    def run(
        self,
        review_date: str,
        sessions: Optional[List[Dict[str, Any]]] = None,
        conversations: Optional[List[Dict[str, Any]]] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        open_problems: Optional[List[Dict[str, Any]]] = None,
    ) -> NightlyMemoryResult:
        sessions = sessions if sessions is not None else []
        conversations = conversations if conversations is not None else []
        memories = memories if memories is not None else []
        open_problems = open_problems if open_problems is not None else []

        payload = {
            "review_date": review_date,
            "sessions": sessions,
            "conversations": conversations,
            "existing_memories": memories,
            "open_problems": open_problems,
        }
        try:
            prompt = self.prompt_registry.get("nightly_memory_update")
        except (FileNotFoundError, KeyError) as exc:
            error_message = f"Prompt file is missing: {exc}"
            return self.failed_result(error_message, conversations, raw_response="")

        user_message = (
            "Generate the nightly memory update JSON for this data:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )

        try:
            output, raw_response = self.run_langchain_structured(prompt, user_message)
            return NightlyMemoryResult(
                output=output,
                raw_response=raw_response,
                parse_status="success",
                error_message="",
            )
        except LLMConfigError as exc:
            error_message = f"LangChain is not configured: {exc}"
        except Exception as exc:
            error_message = f"LangChain structured output failed: {exc}"
        return self.failed_result(error_message, conversations, raw_response="")

    def run_langchain_structured(
        self,
        system_prompt: str,
        user_message: str,
    ) -> tuple[NightlyMemoryUpdateOutput, str]:
        output = run_structured_agent(
            NightlyMemoryUpdateOutput,
            user_message,
            system_prompt=system_prompt,
            settings=self.settings,
            temperature=0.2,
        )
        return output, json.dumps(output.model_dump(), ensure_ascii=False)

    def failed_result(
        self,
        reason: str,
        conversations: List[Dict[str, Any]],
        raw_response: str,
    ) -> NightlyMemoryResult:
        return NightlyMemoryResult(
            output=self.build_fallback_output(reason, conversations),
            raw_response=raw_response,
            parse_status="failed",
            error_message=reason,
        )

    def build_fallback_output(
        self,
        reason: str,
        conversations: List[Dict[str, Any]],
    ) -> NightlyMemoryUpdateOutput:
        message_count = len(conversations)
        if message_count:
            daily_summary = (
                f"今晚记忆更新未能完成结构化分析：{reason} "
                f"今天共有 {message_count} 条对话记录，已保存本次复盘记录供后续检查。"
            )
        else:
            daily_summary = (
                f"今晚记忆更新未能完成结构化分析：{reason} 今天没有可复盘的对话记录。"
            )

        return NightlyMemoryUpdateOutput(
            daily_summary=daily_summary,
            key_events=[],
            discovered_problems=[],
            memory_updates=[],
            next_actions=[
                {
                    "action_type": "follow_up",
                    "content": "检查 LLM 配置或模型 JSON 输出格式后，重新生成今晚记忆更新。",
                    "related_problem": "",
                    "priority": 3,
                }
            ],
        )
