import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


def render_fortune_card(settings: Settings) -> None:
    workflow = PlanningWorkflow(settings)

    col_a, col_b = st.columns(2)
    if col_a.button("抽每日签", use_container_width=True, key="fortune_daily"):
        with st.spinner("正在生成每日签..."):
            st.session_state.latest_fortune_item = workflow.generate_daily_sign()
            st.session_state.latest_fortune_kind = "daily_sign"
    if col_b.button("生成随机小任务", use_container_width=True, key="fortune_random"):
        with st.spinner("正在生成随机小任务..."):
            st.session_state.latest_fortune_item = workflow.generate_random_task()
            st.session_state.latest_fortune_kind = "random_task"

    user_state = st.text_input("当前状态", key="fortune_state")
    if st.button("生成安抚签", key="fortune_soothing"):
        with st.spinner("正在生成安抚签..."):
            st.session_state.latest_fortune_item = workflow.generate_soothing_task(
                user_state or "低能量"
            )
            st.session_state.latest_fortune_kind = "soothing_task"

    item = st.session_state.get("latest_fortune_item")
    kind = st.session_state.get("latest_fortune_kind")
    if item:
        st.markdown("**最新签**")
        st.json(item)
        title = item.get("action") or item.get("title") or item.get("sign_text")
        subject = item.get("subject", "")
        minutes = int(item.get("estimated_minutes") or 0)
        if title and st.button("加入今日任务", key="fortune_add_task"):
            workflow.create_task(
                title=str(title),
                subject=str(subject),
                estimated_minutes=minutes,
                source=str(kind or "fortune_card"),
                scheduled_date=local_today(),
            )
            st.success("已加入今日任务。")

    history = WorkspaceWorkflow().list_fortune_items(limit=30)
    if history:
        st.markdown("**最近签记录**")
        st.dataframe(history, use_container_width=True)
    else:
        st.info("还没有运势签记录。")
