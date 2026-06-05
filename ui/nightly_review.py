from datetime import datetime

import streamlit as st

from agents.nightly_memory_agent import NightlyMemoryAgent
from db.database import (
    create_memory,
    create_nightly_review,
    create_problem,
    get_memories,
    get_conversations_by_date,
    get_open_problems,
    get_sessions_by_date,
)


def today_str():
    return datetime.now().astimezone().date().isoformat()


def run_nightly_memory_update(settings):
    review_date = today_str()
    sessions = get_sessions_by_date(review_date)
    conversations = get_conversations_by_date(review_date)
    memories = get_memories()
    open_problems = get_open_problems()

    agent_result = NightlyMemoryAgent(settings).run(
        review_date=review_date,
        sessions=sessions,
        conversations=conversations,
        memories=memories,
        open_problems=open_problems,
    )
    result = agent_result.result
    review_id = create_nightly_review(
        review_date=review_date,
        result=result,
        raw_response=agent_result.raw_response,
        parse_status=agent_result.parse_status,
    )

    inserted_problem_ids = [
        create_problem(problem, review_id=review_id)
        for problem in result.get("discovered_problems", [])
        if isinstance(problem, dict)
    ]

    inserted_memory_ids = []
    for memory in result.get("memory_updates", []):
        if not isinstance(memory, dict):
            continue
        memory_id = create_memory(memory, review_id=review_id)
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
        f"sessions={review['sessions_count']} | "
        f"conversations={review['conversations_count']}"
    )
    st.caption(
        f"inserted_problems={review['inserted_problem_ids']} | "
        f"inserted_memories={review['inserted_memory_ids']}"
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
