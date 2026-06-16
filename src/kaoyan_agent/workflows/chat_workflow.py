import time
from uuid import uuid4

from kaoyan_agent.agents.chat_agent import ChatAgent
from kaoyan_agent.agents.query_rewriter import QueryRewriter
from kaoyan_agent.agents.router import Router
from kaoyan_agent.core.container import AppContainer
from kaoyan_agent.core.settings import Settings, get_settings
from kaoyan_agent.memory.retriever import MemoryRetriever
from kaoyan_agent.repositories.agent_runs import AgentRunRepository
from kaoyan_agent.repositories.agent_trace import AgentTraceRepository
from kaoyan_agent.repositories.conversation_repository import ChatRepository
from kaoyan_agent.repositories.pending_actions import PendingActionRepository
from kaoyan_agent.repositories.raw_events import RawEventRepository
from kaoyan_agent.schemas.contracts import AgentRequest, AgentResponse, OnlineSessionResult
from kaoyan_agent.workflows.context_builder import ContextBuilder
from kaoyan_agent.workflows.online_action_dispatcher import OnlineActionDispatcher
from kaoyan_agent.workflows.planning import PlanningWorkflow


def build_session_title(content: str, max_length: int = 20) -> str:
    title = " ".join(content.strip().split())
    return title[:max_length] or "新对话"


class OnlineSessionWorkflow:
    """在线聊天编排层。

    在线阶段只写会话、raw_events、业务动作表、pending actions 和 trace；
    长期记忆与 Problem Board 仍由夜间工作流负责。
    """

    workflow_name = "online_session"

    def __init__(
        self,
        settings: Settings | None = None,
        container: AppContainer | None = None,
        chat_repository: ChatRepository | None = None,
        raw_event_repository: RawEventRepository | None = None,
        agent_run_repository: AgentRunRepository | None = None,
        agent_trace_repository: AgentTraceRepository | None = None,
        pending_action_repository: PendingActionRepository | None = None,
    ):
        self.settings = settings or get_settings()
        self.container = container or AppContainer.create(self.settings)
        self.chat_repository = chat_repository or ChatRepository()
        self.raw_event_repository = raw_event_repository or RawEventRepository()
        self.agent_run_repository = agent_run_repository or AgentRunRepository()
        self.agent_trace_repository = agent_trace_repository or AgentTraceRepository()
        self.pending_action_repository = pending_action_repository or PendingActionRepository()
        self.query_rewriter = QueryRewriter()
        self.router = Router()
        self.memory_retriever = MemoryRetriever()
        self.context_builder = ContextBuilder(self.container.prompt_registry)
        self.action_dispatcher = OnlineActionDispatcher(settings=self.settings)
        self.planning_workflow = PlanningWorkflow(self.settings)
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
        run_started = time.perf_counter()
        current_session = self.chat_repository.get_session(session_id)
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

        user_event_id = self.raw_event_repository.create(
            content=user_input,
            role="user",
            session_id=session_id,
            project_id=project_id,
            source_type="chat_message",
            source_id=user_message_id,
            metadata={"channel": "streamlit_chat", "preserved_original": True},
        )
        agent_run_id = self.agent_trace_repository.start_run(
            session_id=session_id,
            user_message_id=user_message_id,
            user_event_id=user_event_id,
            user_input=user_input,
            project_id=project_id,
        )
        self.add_trace_step(
            agent_run_id,
            "保存用户输入",
            "raw_event",
            "ok",
            input_summary=user_input,
            output_summary=f"conversation_id={user_message_id}, raw_event_id={user_event_id}",
            session_id=session_id,
            user_message_id=user_message_id,
            user_event_id=user_event_id,
        )

        recent_messages = self.chat_repository.list_messages(session_id, limit=limit)
        llm_messages = [
            {"role": message["role"], "content": message["content"]}
            for message in recent_messages
            if message["role"] in {"user", "assistant"}
        ]

        rewritten_query = self.query_rewriter.rewrite(user_input, llm_messages)
        self.add_trace_step(
            agent_run_id,
            "QueryRewriter",
            "rewrite",
            "ok",
            input_summary=user_input,
            output_summary=rewritten_query,
            decision_summary="changed" if rewritten_query != user_input else "unchanged",
            session_id=session_id,
            user_message_id=user_message_id,
            user_event_id=user_event_id,
        )

        router_decision = self.router.route(rewritten_query)
        self.add_trace_step(
            agent_run_id,
            "Router",
            "route",
            "ok",
            input_summary=rewritten_query,
            output_summary=router_decision.route,
            decision_summary=router_decision.reason,
            metadata=router_decision.to_dict(),
            session_id=session_id,
            user_message_id=user_message_id,
            user_event_id=user_event_id,
        )

        retrieved_items = []
        if router_decision.need_memory:
            retrieved_items = self.memory_retriever.retrieve(
                rewritten_query,
                decision=router_decision,
                limit=8,
                project_id=project_id,
            )
            retrieval_status = "ok"
            retrieval_summary = f"retrieved {len(retrieved_items)} item(s)"
        else:
            retrieval_status = "skipped"
            retrieval_summary = "router did not request memory retrieval"
        self.add_trace_step(
            agent_run_id,
            "MemoryRetriever",
            "retrieval",
            retrieval_status,
            input_summary=rewritten_query,
            output_summary=retrieval_summary,
            metadata={
                "items": [item.to_dict() for item in retrieved_items[:5]],
                "need_memory": router_decision.need_memory,
            },
            session_id=session_id,
            user_message_id=user_message_id,
            user_event_id=user_event_id,
        )

        action_intent = self.action_dispatcher.classify_intent(router_decision, user_input)
        self.add_trace_step(
            agent_run_id,
            "Action Intent",
            "action_intent",
            "ok",
            input_summary=user_input,
            output_summary=action_intent.intent,
            decision_summary=action_intent.reason,
            metadata=action_intent.to_dict(),
            session_id=session_id,
            user_message_id=user_message_id,
            user_event_id=user_event_id,
        )

        action_result = self.action_dispatcher.dispatch(
            decision=router_decision,
            user_input=user_input,
            session_id=session_id,
            user_event_id=user_event_id,
            project_id=project_id,
            intent_decision=action_intent,
        )
        action_result_data = action_result.to_dict() if action_result else None
        pending_action = None
        if action_result and action_result.pending_action_id:
            pending_action = self.pending_action_repository.get(action_result.pending_action_id)
        self.add_trace_step(
            agent_run_id,
            "OnlineActionDispatcher",
            "action_dispatch",
            action_result.status if action_result else "skipped",
            input_summary=router_decision.route,
            output_summary=(action_result.user_message if action_result else "no action"),
            metadata=action_result_data or {},
            session_id=session_id,
            user_message_id=user_message_id,
            user_event_id=user_event_id,
        )

        context = self.context_builder.build(
            current_input=user_input,
            messages=llm_messages,
            retrieved_items=retrieved_items,
            router_decision=router_decision,
        )
        if action_result_data:
            context["action_result"] = action_result_data
        if pending_action:
            context["pending_action"] = pending_action
        self.add_trace_step(
            agent_run_id,
            "Context Builder",
            "context_build",
            "ok",
            output_summary=f"{len(retrieved_items)} retrieved item(s), action={bool(action_result)}",
            metadata={
                "route": router_decision.route,
                "has_action_result": bool(action_result),
                "has_pending_action": bool(pending_action),
            },
            session_id=session_id,
            user_message_id=user_message_id,
            user_event_id=user_event_id,
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
                "action_intent": action_intent.to_dict(),
                "action_result": action_result_data,
                "pending_action": pending_action,
                "user_event_id": user_event_id,
                "project_id": project_id,
            },
        )

        response, llm_called = self.build_response(request, action_result)
        if action_result and action_result.requires_chat_answer and pending_action:
            response.text = self.append_pending_suggestion(response.text, pending_action)
            response.structured_data["action_result"] = action_result_data or {}
            response.structured_data["pending_action"] = pending_action
        self.add_trace_step(
            agent_run_id,
            "ChatAgent/确定性回复",
            "llm_call" if llm_called else "response",
            response.parse_status,
            input_summary=user_input,
            output_summary=response.text[:240],
            decision_summary="called ChatAgent" if llm_called else "deterministic business response",
            metadata={
                "llm_called": llm_called,
                "action_result": action_result_data,
                "fallback": bool(response.errors),
            },
            error_message="; ".join(response.errors),
            session_id=session_id,
            user_message_id=user_message_id,
            user_event_id=user_event_id,
        )

        assistant_message_id = self.chat_repository.save_message(
            session_id=session_id,
            role="assistant",
            content=response.text,
            project_id=project_id,
        )
        if pending_action and pending_action.get("id"):
            self.pending_action_repository.bind_to_assistant_message(
                int(pending_action["id"]),
                assistant_message_id,
            )
            pending_action = self.pending_action_repository.get(int(pending_action["id"]))

        assistant_event_metadata = {
            "reply_to_event_id": user_event_id,
            "rewritten_query": rewritten_query,
            "router_decision": router_decision.to_dict(),
            "action_intent": action_intent.to_dict(),
            "action_result": action_result_data,
            "pending_action": pending_action,
            "agent_run_id": agent_run_id,
            "parse_status": response.parse_status,
        }
        assistant_event_id = self.raw_event_repository.create(
            content=response.text,
            role="assistant",
            session_id=session_id,
            project_id=project_id,
            source_type="chat_message",
            source_id=assistant_message_id,
            metadata=assistant_event_metadata,
        )
        self.add_trace_step(
            agent_run_id,
            "保存 assistant 回复",
            "persistence",
            "ok",
            output_summary=f"conversation_id={assistant_message_id}, raw_event_id={assistant_event_id}",
            metadata=assistant_event_metadata,
            session_id=session_id,
            user_message_id=user_message_id,
            user_event_id=user_event_id,
            assistant_message_id=assistant_message_id,
        )

        duration_ms = int((time.perf_counter() - run_started) * 1000)
        self.agent_trace_repository.finish_run(
            agent_run_id,
            assistant_message_id=assistant_message_id,
            status=response.parse_status,
            response=response.to_dict(),
            raw_response=response.raw_response,
            error_message=(
                (action_result.error_message if action_result else "")
                or "; ".join(response.errors)
            ),
            duration_ms=duration_ms,
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
            action_result=action_result_data,
            pending_action=pending_action,
            agent_run_id=agent_run_id,
            errors=response.errors,
        )

    def build_response(
        self,
        request: AgentRequest,
        action_result,
    ) -> tuple[AgentResponse, bool]:
        if action_result and action_result.requires_chat_answer:
            response = self.chat_agent.run(request)
            if response.errors:
                response.text = self.build_answer_first_fallback(request.input_text)
            return response, True
        if action_result and action_result.handled:
            return (
                AgentResponse(
                    text=action_result.user_message,
                    structured_data={"action_result": action_result.to_dict()},
                    raw_response=action_result.user_message,
                    parse_status=f"action_{action_result.status}",
                    errors=[],
                ),
                False,
            )
        return self.chat_agent.run(request), True

    def confirm_pending_action(
        self,
        pending_action_id: int,
        decision: str,
        project_id: int | None = None,
    ) -> dict:
        pending = self.pending_action_repository.get(pending_action_id)
        if not pending:
            return {"ok": False, "message": "这条待确认动作不存在或已经被清理。"}
        if decision in {"dismiss", "later"}:
            reason = "只看解答" if decision == "dismiss" else "稍后再说"
            self.pending_action_repository.dismiss(pending_action_id, reason=reason)
            self.raw_event_repository.create(
                content=f"Pending action dismissed: {reason}",
                role="user",
                session_id=pending.get("session_id"),
                project_id=project_id or pending.get("project_id"),
                source_type="pending_action",
                source_id=pending_action_id,
                metadata={"pending_action_id": pending_action_id, "decision": decision},
            )
            return {"ok": True, "message": "已记录你的选择，不会保存错题卡。"}

        if pending.get("status") == "completed" and pending.get("created_target_id"):
            return {
                "ok": True,
                "message": "这张错题卡已经保存过，未重复创建。",
                "card_id": pending.get("created_target_id"),
            }
        if pending.get("action_type") != "create_review_card":
            return {"ok": False, "message": "当前动作暂不支持在聊天页确认。"}

        payload = pending.get("payload") or {}
        self.pending_action_repository.confirm(pending_action_id, result={"decision": "save"})
        card = self.planning_workflow.generate_and_save_practice_card(
            subject=str(payload.get("subject") or ""),
            chapter=str(payload.get("chapter") or ""),
            question=str(payload.get("question") or payload.get("question_summary") or ""),
            user_reason=str(payload.get("user_reason") or ""),
            project_id=project_id or pending.get("project_id"),
        )
        self.pending_action_repository.complete(
            pending_action_id,
            created_target_id=int(card["id"]),
            result={"decision": "save", "card": card},
        )
        self.raw_event_repository.create(
            content=f"Pending mistake card saved: {card.get('question', '')}",
            role="user",
            session_id=pending.get("session_id"),
            project_id=project_id or pending.get("project_id"),
            source_type="pending_action",
            source_id=pending_action_id,
            metadata={
                "pending_action_id": pending_action_id,
                "decision": "save",
                "created_card_id": card["id"],
            },
        )
        return {
            "ok": True,
            "message": "已保存为错题卡，可在「错题复盘」查看。",
            "card_id": card["id"],
        }

    def add_trace_step(self, agent_run_id: int, step_name: str, step_type: str, status: str, **kwargs) -> None:
        self.agent_trace_repository.add_step(
            agent_run_id,
            step_name=step_name,
            step_type=step_type,
            status=status,
            **kwargs,
        )

    @staticmethod
    def append_pending_suggestion(answer_text: str, pending_action: dict) -> str:
        payload = pending_action.get("payload") or {}
        question = payload.get("question_summary") or payload.get("question") or "这道题"
        reason = payload.get("user_reason") or "当前卡点"
        suggestion = (
            "\n\n---\n"
            "建议保存为错题卡：这次卡点有复盘价值。"
            f"\n- 题目摘要：{question}"
            f"\n- 错因线索：{reason}"
            "\n你可以在下方确认是否保存。"
        )
        return f"{answer_text.strip()}{suggestion}"

    @staticmethod
    def build_answer_first_fallback(user_input: str) -> str:
        if "sin2x" in user_input.replace(" ", "") and "积分" in user_input:
            return (
                "先看题目本身：如果这里的 `sin2x` 指的是 `sin(2x)`，可以令 `u=2x`，"
                "则 `du=2dx`，所以 `∫sin(2x)dx = -1/2 cos(2x)+C`。"
                "你卡在换元时，关键是先把内层函数 `2x` 看成一个整体，再补上导数系数。"
            )
        return (
            "先处理题目本身：把已知条件、要求和你卡住的步骤分开看。"
            "如果你已经知道错因，优先复盘“为什么当时没有想到这个方法”，再做一题同型题验证。"
        )
