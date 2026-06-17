import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.repositories.agent_trace import AgentTraceRepository
from kaoyan_agent.repositories.conversation_repository import ChatRepository
from kaoyan_agent.repositories.pending_actions import PendingActionRepository
from kaoyan_agent.ui.components.common import (
    inject_global_styles,
    mistake_reason_label,
    render_card,
    render_json_debug_expander,
    render_page_header,
    render_status_badge,
)
from kaoyan_agent.workflows.chat_workflow import OnlineSessionWorkflow


def ensure_current_session(
    chat_repository: ChatRepository,
    session_id: int | None = None,
) -> int:
    candidate_id = session_id or st.session_state.get("current_chat_session_id")
    if candidate_id:
        session = chat_repository.get_session(int(candidate_id))
        if session:
            st.session_state.current_chat_session_id = int(candidate_id)
            return int(candidate_id)

    new_session_id = chat_repository.create_session()
    st.session_state.current_chat_session_id = new_session_id
    return new_session_id


def render_chat_page(
    settings: Settings,
    session_id: int | None = None,
) -> None:
    chat_repository = ChatRepository()
    pending_repository = PendingActionRepository()
    trace_repository = AgentTraceRepository()
    current_session_id = ensure_current_session(
        chat_repository=chat_repository,
        session_id=session_id,
    )
    current_session = chat_repository.get_session(current_session_id)

    inject_global_styles()
    render_page_header(
        "聊天",
        "你可以问学习问题，也可以明确说开始番茄钟、创建今日任务、生成错题卡。",
    )
    st.caption(
        current_session["title"]
        if current_session
        else chat_repository.default_session_title
    )

    messages = chat_repository.list_messages(current_session_id, limit=50)
    if not messages:
        render_quick_prompt_cards()
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                render_pending_actions_for_message(
                    settings, pending_repository, int(message["id"])
                )
                render_trace_for_message(trace_repository, int(message["id"]))

    prompt = st.chat_input("输入学习问题、复盘记录、计划变化或当前状态。")
    if not prompt:
        return

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("处理中..."):
            result = OnlineSessionWorkflow(settings).handle_user_message(
                session_id=current_session_id,
                user_input=prompt,
                limit=20,
            )
        st.markdown(result.assistant_text)
        render_pending_actions_for_message(
            settings, pending_repository, result.assistant_message_id
        )
        render_trace_for_message(trace_repository, result.assistant_message_id)
        if result.errors:
            st.caption("本次回复使用了备用处理。")
            render_json_debug_expander("开发调试信息", {"errors": result.errors})


def render_quick_prompt_cards() -> None:
    col_focus, col_task, col_review = st.columns(3)
    with col_focus:
        render_card(
            "开始番茄钟",
            "我想专注 15 分钟学习数学积分",
            badge="专注",
        )
    with col_task:
        render_card(
            "创建任务",
            "帮我创建一个 15 分钟操作系统任务",
            badge="计划",
        )
    with col_review:
        render_card(
            "先问题，再确认错题卡",
            "sin(2x) 积分我不会，原因是不会换元",
            badge="复盘",
        )


def render_pending_actions_for_message(
    settings: Settings,
    pending_repository: PendingActionRepository,
    assistant_message_id: int,
) -> None:
    pending_actions = pending_repository.list_for_message(assistant_message_id)
    for pending in pending_actions:
        if pending.get("action_type") != "create_review_card":
            continue
        payload = pending.get("payload") or {}
        st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="kaoyan-card-title">建议保存为错题卡</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<span class="kaoyan-badge">{render_status_badge(pending.get("status", ""))}</span>'
            f'<span class="kaoyan-badge">{payload.get("subject") or "未指定科目"}</span>'
            f'<span class="kaoyan-badge">{payload.get("chapter") or "未指定章节"}</span>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"**题目摘要：** {payload.get('question_summary') or payload.get('question') or '未填写'}"
        )
        st.markdown(f"**错因线索：** {payload.get('user_reason') or '待确认'}")
        st.markdown(
            f"**错因分类：** {mistake_reason_label(payload.get('mistake_reason', 'unknown'))}"
        )
        st.markdown(f"**复习优先级：** {payload.get('review_priority') or 3}")
        status = str(pending.get("status") or "")
        if status == "pending_confirmation":
            col_save, col_answer, col_later = st.columns(3)
            workflow = OnlineSessionWorkflow(settings)
            if col_save.button("保存为错题卡", key=f"save_pending_{pending['id']}"):
                result = workflow.confirm_pending_action(int(pending["id"]), "save")
                show_pending_result(result)
                st.rerun()
            if col_answer.button("只看解答", key=f"dismiss_pending_{pending['id']}"):
                result = workflow.confirm_pending_action(int(pending["id"]), "dismiss")
                show_pending_result(result)
                st.rerun()
            if col_later.button("稍后再说", key=f"later_pending_{pending['id']}"):
                result = workflow.confirm_pending_action(int(pending["id"]), "later")
                show_pending_result(result)
                st.rerun()
        elif status == "completed":
            st.success("已保存为错题卡，可在「错题复盘」查看。")
        elif status == "dismissed":
            st.info("已按你的选择保留解答，不保存错题卡。")
        st.markdown("</div>", unsafe_allow_html=True)


def show_pending_result(result: dict) -> None:
    if result.get("ok"):
        st.success(result.get("message", "操作已完成。"))
    else:
        st.warning(result.get("message", "当前无法处理这个动作。"))


def render_trace_for_message(
    trace_repository: AgentTraceRepository,
    assistant_message_id: int,
) -> None:
    run = trace_repository.get_run_by_message(assistant_message_id)
    if not run:
        return
    steps = trace_repository.list_steps(int(run["id"]))
    with st.expander("查看执行过程", expanded=False):
        response = run.get("response") or {}
        structured = response.get("structured_data") or {}
        action_result = structured.get("action_result") or {}
        st.caption(
            f"状态：{run.get('parse_status', '')} / "
            f"耗时：{int(run.get('duration_ms') or 0)} ms / "
            f"动作：{action_result.get('action_type') or '无'}"
        )
        for step in steps:
            st.markdown(
                f"**{int(step.get('step_order') or 0)}. {step.get('step_name')}** "
                f"({step.get('status')})"
            )
            if step.get("decision_summary"):
                st.caption(step["decision_summary"])
            if step.get("output_summary"):
                st.write(step["output_summary"])
        debug = {
            "run_id": run.get("id"),
            "route": extract_route_from_steps(steps),
            "action_result": action_result,
            "retrieved_preview": extract_retrieval_preview(steps),
        }
        render_json_debug_expander("开发调试信息", debug)


def extract_route_from_steps(steps: list[dict]) -> str:
    for step in steps:
        if step.get("step_type") == "route":
            return str(step.get("output_summary") or "")
    return ""


def extract_retrieval_preview(steps: list[dict]) -> list[dict]:
    for step in steps:
        if step.get("step_type") == "retrieval":
            metadata = step.get("metadata") or {}
            return list(metadata.get("items") or [])[:3]
    return []
