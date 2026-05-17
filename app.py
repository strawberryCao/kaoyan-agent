from datetime import datetime

import streamlit as st

from agents.chat_agent import ChatAgent
from agents.nightly_memory_agent import NightlyMemoryAgent
from config import get_settings
from db.database import (
    DEFAULT_SESSION_TITLE,
    create_chat_session,
    get_all_memories,
    get_chat_session,
    get_chat_sessions,
    get_conversations_by_date,
    get_messages_by_session,
    get_open_problems,
    get_sessions_by_date,
    init_db,
    insert_memory,
    insert_problem,
    save_message,
    save_nightly_review,
    update_chat_session_title,
)


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


def today_str():
    return datetime.now().astimezone().date().isoformat()


def run_nightly_memory_update(settings):
    review_date = today_str()
    sessions = get_sessions_by_date(review_date)
    conversations = get_conversations_by_date(review_date)
    memories = get_all_memories()
    open_problems = get_open_problems()

    agent_result = NightlyMemoryAgent(settings).run(
        review_date=review_date,
        sessions=sessions,
        conversations=conversations,
        memories=memories,
        open_problems=open_problems,
    )
    result = agent_result.result
    review_id = save_nightly_review(
        review_date=review_date,
        result=result,
        raw_response=agent_result.raw_response,
        parse_status=agent_result.parse_status,
    )

    inserted_problem_ids = [
        insert_problem(problem, review_id=review_id)
        for problem in result.get("discovered_problems", [])
        if isinstance(problem, dict)
    ]
    inserted_memory_ids = []
    for memory in result.get("memory_updates", []):
        if not isinstance(memory, dict):
            continue
        memory_id = insert_memory(memory, review_id=review_id)
        if memory_id:
            inserted_memory_ids.append(memory_id)

    return {
        "review_id": review_id,
        "review_date": review_date,
        "parse_status": agent_result.parse_status,
        "sessions_count": len(sessions),
        "conversations_count": len(conversations),
        "inserted_problem_ids": inserted_problem_ids,
        "inserted_memory_ids": inserted_memory_ids,
        "result": result,
    }


def render_nightly_result(review):
    st.subheader("今晚记忆更新结果")
    st.caption(
        f"review_id={review['review_id']} | date={review['review_date']} | "
        f"parse_status={review['parse_status']} | "
        f"sessions={review['sessions_count']} | conversations={review['conversations_count']}"
    )

    result = review["result"]
    st.markdown(result.get("daily_summary") or "没有生成 daily_summary。")

    problems = result.get("discovered_problems", [])
    memories = result.get("memory_updates", [])
    next_actions = result.get("next_actions", [])

    if problems:
        st.write("Discovered Problems")
        st.dataframe(problems, use_container_width=True)
    else:
        st.info("本次没有发现可写入 Problem Board 的问题。")

    if memories:
        st.write("Memory Updates")
        st.dataframe(memories, use_container_width=True)
    else:
        st.info("本次没有生成长期记忆更新。")

    if next_actions:
        st.write("Next Actions")
        st.dataframe(next_actions, use_container_width=True)

    with st.expander("Raw JSON result"):
        st.json(result)


st.set_page_config(page_title="Kaoyan Problem Discovery Agent")

settings = get_settings()
init_db()
current_session_id = ensure_current_session()
current_session = get_chat_session(current_session_id)

st.title("Kaoyan Problem Discovery Agent")

with st.sidebar:
    st.caption("V0.2")
    st.write(f"Model: `{settings.llm_model}`")
    st.write(f"Database: `{settings.database_path}`")

    if st.button("新建对话", use_container_width=True):
        st.session_state.current_session_id = create_chat_session()
        st.rerun()

    if st.button("生成今晚记忆更新", use_container_width=True):
        with st.spinner("正在生成今晚记忆更新..."):
            st.session_state.latest_nightly_review = run_nightly_memory_update(settings)
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
            assistant_text = ChatAgent(settings).respond(current_session_id, limit=20)
        st.markdown(assistant_text)

    save_message(current_session_id, "assistant", assistant_text)

if "latest_nightly_review" in st.session_state:
    st.divider()
    render_nightly_result(st.session_state.latest_nightly_review)

st.divider()
st.subheader("Problem Board")
open_problems = get_open_problems()
if open_problems:
    st.dataframe(open_problems, use_container_width=True)
else:
    st.caption("暂无 open 状态问题。")

st.subheader("Memories")
memories = get_all_memories()
if memories:
    st.dataframe(memories, use_container_width=True)
else:
    st.caption("暂无长期记忆。")
