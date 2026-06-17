import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import render_page_header
from kaoyan_agent.ui.components.task_panel import render_task_panel


def render_task_page(settings: Settings) -> None:
    render_page_header(
        "今日作战台",
        "今天只看最重要的任务、专注和问题提醒。",
        badge="主入口",
    )

    with st.spinner("加载今日任务..."):
        render_task_panel(settings)
