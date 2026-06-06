import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.workflows.nightly_memory_workflow import NightlyMemoryWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


def render_nightly_review_panel(settings: Settings) -> None:
    review_date = st.date_input("回顾日期", key="nightly_date").isoformat()
    if st.button("运行晚间回顾", type="primary", key="nightly_run"):
        with st.spinner("正在运行 Nightly Memory Update..."):
            result = NightlyMemoryWorkflow(settings).run(
                review_date=review_date or local_today(),
            )
        st.session_state.latest_nightly_review = result.to_dict()

    result = st.session_state.get("latest_nightly_review")
    if result:
        st.metric("Review ID", result.get("review_id", "-"))
        st.metric("原始证据数", result.get("raw_events_count", 0))
        st.metric("写入问题数", len(result.get("inserted_problem_ids") or []))
        st.metric("写入记忆数", len(result.get("inserted_memory_ids") or []))
        st.caption(f"结构化解析状态：{result.get('parse_status', 'unknown')}")
        if result.get("parse_status") == "failed":
            st.warning("本次结构化解析失败，已保存 raw_response 和 error_message，未写入问题板或长期记忆。")
            if result.get("error_message"):
                st.caption(result["error_message"])
        payload = result.get("result") or {}
        if payload.get("daily_summary"):
            st.markdown("**当天总结**")
            st.write(payload["daily_summary"])
        if payload.get("key_events"):
            st.markdown("**关键事件**")
            st.write(payload["key_events"])
        if payload.get("discovered_problems"):
            st.markdown("**候选问题**")
            st.dataframe(payload["discovered_problems"], use_container_width=True)
        if payload.get("memory_updates"):
            st.markdown("**候选记忆**")
            st.dataframe(payload["memory_updates"], use_container_width=True)

    latest = WorkspaceWorkflow().list_latest_reviews(limit=5)
    if latest:
        st.markdown("**最近晚间回顾**")
        st.dataframe(latest, use_container_width=True)
    else:
        st.info("还没有晚间回顾记录。")
