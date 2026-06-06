from typing import Dict, List

from kaoyan_agent.prompts.prompt_registry import PromptRegistry
from kaoyan_agent.schemas.contracts import RetrievedItem, RouterDecision


class ContextBuilder:
    """把路由、检索结果和会话消息组装成 ChatAgent 的上下文。

    这个类只负责拼接 prompt/context，不直接调用 LLM，也不写数据库。
    """

    def __init__(self, prompt_registry: PromptRegistry | None = None):
        self.prompt_registry = prompt_registry or PromptRegistry()

    def build(
        self,
        current_input: str,
        messages: List[Dict[str, str]],
        retrieved_items: List[RetrievedItem],
        router_decision: RouterDecision,
    ) -> Dict[str, object]:
        """构造 AgentRequest.context 使用的结构化上下文。"""

        system_prompt = self.prompt_registry.get("chat")

        if retrieved_items:
            # retrieved context 是回答参考，不代表在线阶段可以直接写长期记忆。
            memory_lines = []
            for item in retrieved_items:
                label = f"{item.source_type}:{item.source_id or '-'}"
                memory_lines.append(f"- [{label} score={item.score}] {item.content}")
            system_prompt += (
                "\n\nRelevant retrieved context:\n"
                + "\n".join(memory_lines)
                + "\nUse this context only when it is relevant to the user's latest message."
            )

        # 路由元数据帮助 ChatAgent 理解当前请求意图，也明确写记忆的边界。
        system_prompt += (
            "\n\nRouting metadata:\n"
            f"- route: {router_decision.route}\n"
            f"- reason: {router_decision.reason}\n"
            "- Online chat must not write long-term memory directly."
        )

        return {
            "system_prompt": system_prompt,
            "messages": messages,
            "current_input": current_input,
            "router_decision": router_decision.to_dict(),
        }

