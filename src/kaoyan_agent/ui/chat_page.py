import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.repositories.conversation_repository import ChatRepository
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

    session_id = chat_repository.create_session()
    st.session_state.current_chat_session_id = session_id
    return session_id


def render_chat_page(
    settings: Settings,
    session_id: int | None = None,
) -> None:
    chat_repository = ChatRepository()
    current_session_id = ensure_current_session(
        chat_repository=chat_repository,
        session_id=session_id,
    )
    current_session = chat_repository.get_session(current_session_id)

    st.title("聊天")
    st.caption("对话是输入渠道；消息会作为原始证据进入晚间问题发现链路。")

    st.caption(
        current_session["title"] if current_session else chat_repository.default_session_title
    )

    messages = chat_repository.list_messages(current_session_id, limit=50)
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("输入学习问题、复盘记录、计划变化或当前状态。")
    if not prompt:
        return

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            result = OnlineSessionWorkflow(settings).handle_user_message(
                session_id=current_session_id,
                user_input=prompt,
                limit=20,
            )
        st.markdown(result.assistant_text)
        if result.errors:
            st.caption("; ".join(result.errors))

