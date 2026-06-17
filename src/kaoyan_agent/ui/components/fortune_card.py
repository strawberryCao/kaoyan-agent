import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import (
    install_card_styles,
    render_json_debug_expander,
    sign_level_label,
)
from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.ui.view_models import to_motivation_view_model
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


def render_fortune_card(settings: Settings) -> None:
    install_card_styles()
    workflow = PlanningWorkflow(settings)
    tab_daily, tab_random, tab_soothing = st.tabs(["每日签", "随机小任务", "安抚启动"])

    with tab_daily:
        if st.button("抽每日签", type="primary", use_container_width=True, key="fortune_daily"):
            with st.spinner("正在生成每日签..."):
                st.session_state.latest_fortune_daily = workflow.generate_daily_sign()
        render_fortune_result(st.session_state.get("latest_fortune_daily"), "daily_sign", workflow)

    with tab_random:
        if st.button("生成随机小任务", type="primary", use_container_width=True, key="fortune_random"):
            with st.spinner("正在生成随机小任务..."):
                st.session_state.latest_fortune_random = workflow.generate_random_task()
        render_fortune_result(st.session_state.get("latest_fortune_random"), "random_task", workflow)

    with tab_soothing:
        user_state = st.text_area("当前状态", value="", height=90, key="fortune_state")
        if st.button("生成安抚签", type="primary", use_container_width=True, key="fortune_soothing"):
            with st.spinner("正在生成安抚签..."):
                st.session_state.latest_fortune_soothing = workflow.generate_soothing_task(
                    user_state or "低能量"
                )
        render_fortune_result(st.session_state.get("latest_fortune_soothing"), "soothing_task", workflow)

    with st.expander("最近签记录", expanded=False):
        history = WorkspaceWorkflow().list_fortune_items(limit=20)
        if history:
            for record in history:
                render_history_item(record)
        else:
            st.info("还没有签记录。")


def render_fortune_result(item: dict | None, kind: str, workflow: PlanningWorkflow) -> None:
    if not item:
        st.info("点击上方按钮生成结果。")
        return
    if item.get("generation_error"):
        st.info("当前使用本地备用结果。")
    render_latest_fortune_item(item, kind)
    render_json_debug_expander(
        "开发调试信息",
        {"generation_error": item.get("generation_error")} if item.get("generation_error") else {},
    )

    title = item.get("action") or item.get("title") or item.get("sign_text")
    subject = item.get("subject", "")
    minutes = int(item.get("estimated_minutes") or 5)
    if title and st.button("加入今日任务", key=f"fortune_add_task_{kind}"):
        workflow.create_task(
            title=str(title),
            subject=str(subject),
            estimated_minutes=max(1, minutes),
            source=str(kind or "fortune_card"),
            scheduled_date=local_today(),
        )
        st.success("已加入今日任务。")


def render_latest_fortune_item(item: dict, kind: str) -> None:
    if kind == "daily_sign":
        st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)
        st.markdown(
            f'<div class="kaoyan-card-title">每日签：{sign_level_label(item.get("sign_level", ""))}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(f"**签文：** {item.get('sign_text', '')}")
        st.markdown(f"**今日建议：** {item.get('today_advice', '')}")
        st.markdown(f"**建议行动：** {item.get('action', '')}")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if kind == "random_task":
        title = "随机小任务"
        action_label = "任务标题"
    else:
        title = "安抚启动"
        action_label = "低门槛行动"

    st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="kaoyan-card-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f"**{action_label}：** {item.get('title', '')}")
    st.markdown(f"**主题/科目：** {item.get('subject', '未指定')}")
    st.markdown(f"**预计时间：** {int(item.get('estimated_minutes') or 5)} 分钟")
    st.markdown(f"**说明：** {item.get('reason', '')}")
    st.markdown("</div>", unsafe_allow_html=True)


def render_history_item(record: dict) -> None:
    vm = to_motivation_view_model(record)
    st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="kaoyan-card-title">{vm["card_type_label"]}</div>', unsafe_allow_html=True)
    st.markdown(f"**内容：** {vm['main_text']}")
    if vm["action"]:
        st.markdown(f"**建议行动：** {vm['action']}")
    if vm["minutes"] > 0:
        st.caption(f"预计时间：{vm['minutes']} 分钟")
    st.markdown("</div>", unsafe_allow_html=True)
