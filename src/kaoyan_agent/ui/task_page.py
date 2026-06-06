import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.task_panel import render_task_panel


def render_task_page(settings: Settings) -> None:
    st.title("今日任务 / 学习规划")
    render_task_panel(settings)
