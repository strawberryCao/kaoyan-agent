from uuid import uuid4

from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.agents.chat_agent import ChatAgent
from kaoyan_agent.agents.query_rewriter import QueryRewriter
from kaoyan_agent.agents.router import Router
from kaoyan_agent.core.container import AppContainer
from kaoyan_agent.memory.retriever import MemoryRetriever
from kaoyan_agent.repositories.agent_runs import AgentRunRepository
from kaoyan_agent.repositories.conversation_repository import ChatRepository
from kaoyan_agent.repositories.raw_events import RawEventRepository
from kaoyan_agent.schemas.contracts import AgentRequest, OnlineSessionResult
from kaoyan_agent.workflows.context_builder import ContextBuilder


def build_session_title(content: str, max_length: int = 20) -> str:
    title = " ".join(content.strip().split())
    return title[:max_length] or "新对话"


class OnlineSessionWorkflow:
    """在线聊天的应用编排层。

    这里负责把一次用户输入串成完整链路：保存对话证据、改写查询、路由、
    按需检索记忆、构造上下文、调用 ChatAgent，并记录 assistant 回复和
    agent_run。长期记忆仍由夜间更新负责，在线聊天只读取相关上下文。
    """

    workflow_name = "online_session"

    def __init__(
        self,
        settings: Settings | None = None,
        container: AppContainer | None = None,
        chat_repository: ChatRepository | None = None,
        raw_event_repository: RawEventRepository | None = None,
        agent_run_repository: AgentRunRepository | None = None,
    ):
        self.settings = settings or get_settings()
        self.container = container or AppContainer.create(self.settings)
        self.chat_repository = chat_repository or ChatRepository()
        self.raw_event_repository = raw_event_repository or RawEventRepository()
        self.agent_run_repository = agent_run_repository or AgentRunRepository()
        self.query_rewriter = QueryRewriter()
        self.router = Router()
        self.memory_retriever = MemoryRetriever()
        self.context_builder = ContextBuilder(self.container.prompt_registry)
        self.chat_agent = ChatAgent(
            llm_client=self.container.llm_client,
            prompt_registry=self.container.prompt_registry,
        )

    def handle_user_message(
        self,
        session_id: int,
        user_input: str,
        project_id: int | None = None,
        user_id: str = "default",
        limit: int = 20,
    ) -> OnlineSessionResult:
        """处理一条用户消息，并返回 UI 需要展示和追踪的运行结果。"""

        current_session = self.chat_repository.get_session(session_id)
        # 先保存原始对话文本，保证后续 LLM 或检索失败时仍有可复盘证据。
        user_message_id = self.chat_repository.save_message(
            session_id=session_id,
            role="user",
            content=user_input,
            project_id=project_id,
        )
        if current_session and current_session.get("title") == self.chat_repository.default_session_title:
            self.chat_repository.update_session_title(
                session_id,
                build_session_title(user_input),
            )

        # raw_events 是夜间 Problem Discovery 的输入证据层，保留来源和元数据。
        user_event_id = self.raw_event_repository.create(
            content=user_input,
            role="user",
            session_id=session_id,
            project_id=project_id,
            source_type="chat_message",
            source_id=user_message_id,
            metadata={"channel": "streamlit_chat", "preserved_original": True},
        )

        # 只把最近一段会话喂给 LLM，避免把整个历史对话无边界塞进上下文。
        recent_messages = self.chat_repository.list_messages(session_id, limit=limit)
        llm_messages = [
            {"role": message["role"], "content": message["content"]}
            for message in recent_messages
            if message["role"] in {"user", "assistant"}
        ]

        # QueryRewriter 和 Router 决定是否需要记忆、计划、文件或搜索等能力。
        rewritten_query = self.query_rewriter.rewrite(user_input, llm_messages)
        router_decision = self.router.route(rewritten_query)
        retrieved_items = []
        if router_decision.need_memory:
            # 在线阶段只检索已存在的 memory/problem，不在这里新增长期记忆。
            retrieved_items = self.memory_retriever.retrieve(
                rewritten_query,
                decision=router_decision,
                limit=8,
                project_id=project_id,
            )

        # ContextBuilder 把路由结果和检索证据注入 prompt，ChatAgent 只负责生成回复。
        context = self.context_builder.build(
            current_input=user_input,
            messages=llm_messages,
            retrieved_items=retrieved_items,
            router_decision=router_decision,
        )
        request = AgentRequest(
            request_id=str(uuid4()),
            user_id=user_id,
            session_id=session_id,
            input_text=user_input,
            context=context,
            retrieved_items=retrieved_items,
            metadata={
                "rewritten_query": rewritten_query,
                "router_decision": router_decision.to_dict(),
                "user_event_id": user_event_id,
                "project_id": project_id,
            },
        )
        response = self.chat_agent.run(request)

        # assistant 回复同样写入 conversations 和 raw_events，方便夜间复盘闭环。
        assistant_message_id = self.chat_repository.save_message(
            session_id=session_id,
            role="assistant",
            content=response.text,
            project_id=project_id,
        )
        assistant_event_id = self.raw_event_repository.create(
            content=response.text,
            role="assistant",
            session_id=session_id,
            project_id=project_id,
            source_type="chat_message",
            source_id=assistant_message_id,
            metadata={
                "reply_to_event_id": user_event_id,
                "rewritten_query": rewritten_query,
                "router_decision": router_decision.to_dict(),
                "parse_status": response.parse_status,
            },
        )
        # agent_runs 记录模型输入输出和解析状态，后续可以排查质量问题。
        agent_run_id = self.agent_run_repository.create(
            agent_name="ChatAgent",
            workflow_name=self.workflow_name,
            request=request.to_dict(),
            response=response.to_dict(),
            raw_response=response.raw_response,
            parse_status=response.parse_status,
            error_message="; ".join(response.errors),
            project_id=project_id,
        )

        return OnlineSessionResult(
            session_id=session_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            user_event_id=user_event_id,
            assistant_event_id=assistant_event_id,
            assistant_text=response.text,
            rewritten_query=rewritten_query,
            router_decision=router_decision,
            retrieved_items=retrieved_items,
            agent_run_id=agent_run_id,
            errors=response.errors,
        )

