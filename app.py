import streamlit as st

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
from services.llm_client import LLMClient, LLMConfigError


def get_recent_chat_messages(session_id, limit=20):
    messages = get_messages_by_session(session_id, limit=limit)
    return [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if message["role"] in {"user", "assistant"}
    ]


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


st.set_page_config(page_title="Kaoyan Problem Discovery Agent", page_icon="💬")

settings = get_settings()
init_db()
current_session_id = ensure_current_session()
current_session = get_chat_session(current_session_id)

st.title("Kaoyan Problem Discovery Agent")
st.caption("对话首页 · 侧边栏可切换到「今日作战台」「督学模式」「专注统计」")

with st.sidebar:
    st.caption("V0.1.5")
    st.write(f"Model: `{settings.llm_model}`")
    st.write(f"Database: `{settings.database_path}`")

    if st.button("新建对话", use_container_width=True):
        st.session_state.current_session_id = create_chat_session()
        st.rerun()

    st.divider()
    st.subheader("历史对话")
    for session in get_chat_sessions(limit=30):
        label = session["title"] or DEFAULT_SESSION_TITLE
        if session["id"] == current_session_id:
            label = f"✓ {label}"
        if st.button(label, key=f"session_{session['id']}", use_container_width=True):
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
            try:
                assistant_text = LLMClient(settings).chat(
                    get_recent_chat_messages(current_session_id, limit=20)
                )
            except LLMConfigError as exc:
                assistant_text = f"LLM is not configured: {exc}"
            except Exception as exc:
                assistant_text = f"LLM request failed: {exc}"

        st.markdown(assistant_text)

    save_message(current_session_id, "assistant", assistant_text)
