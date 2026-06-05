import streamlit as st

from agents.chat_agent import ChatAgent
from config import get_settings
from db.database import (
    DEFAULT_SESSION_TITLE,
    create_chat_session,
    get_chat_session,
    get_chat_sessions,
    get_messages_by_session,
    init_db,
    save_message,
    update_chat_session_title,
)
from ui.demo_pages import (
    render_checkpoint_page,
    render_mistake_review_pool,
    render_sign_and_random_task_page,
    render_today_dashboard,
)
from ui.nightly_review import render_nightly_result, run_nightly_memory_update


def build_session_title(content, max_length=20):
    title = " ".join(content.strip().split())
    return title[:max_length] or DEFAULT_SESSION_TITLE


def ensure_current_session():
    session_id = st.session_state.get("current_session_id")
    if session_id and get_chat_session(session_id):
        return session_id

    session_id = create_chat_session()
    st.session_state.current_session_id = session_id
    return session_id


def render_chat_page(settings):
    current_session_id = ensure_current_session()
    current_session = get_chat_session(current_session_id)

    st.title("Kaoyan Problem Discovery Agent")

    st.subheader("Nightly Memory Update")
    st.caption("从今天的对话、已有记忆和 open problems 中生成夜间回顾。")
    if st.button("生成夜间回顾", type="primary", use_container_width=True):
        with st.spinner("正在生成夜间回顾..."):
            st.session_state.latest_nightly_review = run_nightly_memory_update(settings)

    if "latest_nightly_review" in st.session_state:
        render_nightly_result(st.session_state.latest_nightly_review)

    st.divider()

    with st.sidebar:
        st.divider()
        if st.button("新建对话", use_container_width=True):
            st.session_state.current_session_id = create_chat_session()
            st.rerun()

        st.subheader("历史对话")
        for session in get_chat_sessions(limit=30):
            label = session["title"] or DEFAULT_SESSION_TITLE
            if session["id"] == current_session_id:
                label = f"✓ {label}"
            if st.button(
                label,
                key=f"session_{session['id']}",
                use_container_width=True,
            ):
                st.session_state.current_session_id = session["id"]
                st.rerun()

    messages = get_messages_by_session(current_session_id, limit=50)
    st.caption(current_session["title"] if current_session else DEFAULT_SESSION_TITLE)

    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    prompt = st.chat_input("输入学习问题、复盘内容或当前状态")

    if prompt:
        save_message(current_session_id, "user", prompt)
        if current_session and current_session["title"] == DEFAULT_SESSION_TITLE:
            update_chat_session_title(current_session_id, build_session_title(prompt))

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                assistant_text = ChatAgent(settings).respond(current_session_id, limit=20)
            st.markdown(assistant_text)

        save_message(current_session_id, "assistant", assistant_text)


st.set_page_config(page_title="Kaoyan Problem Discovery Agent", layout="wide")

settings = get_settings()
init_db()

with st.sidebar:
    st.caption("V0.4 Demo")
    page = st.radio(
        "页面",
        [
            "聊天",
            "今日作战台",
            "错题复刷池",
            "章节闯关验收",
            "上岸签 / 随机任务",
        ],
    )
    st.divider()
    st.write(f"Model: `{settings.llm_model}`")
    st.write(f"Database: `{settings.database_path}`")

if page == "聊天":
    render_chat_page(settings)
elif page == "今日作战台":
    render_today_dashboard()
elif page == "错题复刷池":
    render_mistake_review_pool(settings)
elif page == "章节闯关验收":
    render_checkpoint_page(settings)
else:
    render_sign_and_random_task_page(settings)
