import streamlit as st

from config import get_settings
from db.database import init_db, list_messages, save_message
from services.llm_client import LLMClient, LLMConfigError


def get_recent_chat_messages(limit=20):
    messages = st.session_state.messages[-limit:]
    return [
        {"role": message["role"], "content": message["content"]}
        for message in messages
        if message["role"] in {"user", "assistant"}
    ]


st.set_page_config(page_title="Kaoyan Problem Discovery Agent")

settings = get_settings()
init_db()

if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": row["role"], "content": row["content"]}
        for row in list_messages(limit=50)
    ]

st.title("Kaoyan Problem Discovery Agent")

with st.sidebar:
    st.caption("V0.1")
    st.write(f"Model: `{settings.llm_model}`")
    st.write(f"Database: `{settings.database_path}`")

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("输入学习问题、复盘内容或当前状态")

if prompt:
    user_message = {"role": "user", "content": prompt}
    st.session_state.messages.append(user_message)
    save_message("user", prompt)

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                assistant_text = LLMClient(settings).chat(get_recent_chat_messages())
            except LLMConfigError as exc:
                assistant_text = f"LLM is not configured: {exc}"
            except Exception as exc:
                assistant_text = f"LLM request failed: {exc}"

        st.markdown(assistant_text)

    st.session_state.messages.append(
        {"role": "assistant", "content": assistant_text}
    )
    save_message("assistant", assistant_text)
