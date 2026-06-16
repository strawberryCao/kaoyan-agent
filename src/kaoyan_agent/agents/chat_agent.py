from typing import Any, Dict, List, Optional

from kaoyan_agent.agents.chat_tools import build_readonly_chat_tools
from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.prompts.prompt_registry import PromptRegistry
from kaoyan_agent.schemas.contracts import AgentRequest, AgentResponse
from kaoyan_agent.services.llm_client import LLMClient, run_text_agent


class ChatAgent:
    def __init__(
        self,
        llm_client: Optional[LLMClient],
        prompt_registry: Optional[PromptRegistry] = None,
    ):
        self.llm_client = llm_client
        self.prompt_registry = prompt_registry or PromptRegistry()

    def run(self, request: AgentRequest) -> AgentResponse:
        messages: List[Dict[str, str]] = request.context.get("messages", [])
        system_prompt = request.context.get("system_prompt") or self.prompt_registry.get(
            "chat"
        )

        try:
            return self.run_langchain_agent(request, messages, system_prompt)
        except Exception as exc:
            return AgentResponse(
                text="当前模型回复不可用，已保留你的问题作为原始证据。你可以稍后重试，或先使用侧边栏学习功能继续操作。",
                raw_response="",
                parse_status="llm_request_error",
                errors=[str(exc)],
            )

    def run_langchain_agent(
        self,
        request: AgentRequest,
        messages: List[Dict[str, str]],
        system_prompt: str,
    ) -> AgentResponse:
        tools = build_readonly_chat_tools(project_id=request.metadata.get("project_id"))
        text = run_text_agent(
            messages,
            system_prompt=system_prompt,
            settings=self.get_settings(),
            temperature=0.3,
            tools=tools,
        )
        if not text:
            raise ValueError("LangChain agent returned an empty response.")

        return AgentResponse(
            text=text,
            raw_response=text,
            confidence=0.8,
            evidence_refs=[item.to_dict() for item in request.retrieved_items],
            structured_data={
                "langchain_agent": True,
                "tool_names": [self.tool_name(tool_item) for tool_item in tools],
            },
        )

    def get_settings(self) -> Settings:
        if self.llm_client:
            return self.llm_client.settings
        return get_settings()

    def tool_name(self, tool_item: Any) -> str:
        return str(
            getattr(tool_item, "name", "")
            or getattr(tool_item, "__name__", "")
            or type(tool_item).__name__
        )
