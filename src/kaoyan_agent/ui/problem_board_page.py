import streamlit as st

from kaoyan_agent.ui.components.common import render_page_header
from kaoyan_agent.ui.components.problem_board_panel import render_problem_board_panel


def render_problem_board_page() -> None:
    render_page_header(
        "问题板",
        "系统持续追踪的学习问题、证据、根因和下一步干预。",
        badge="核心",
    )

    with st.spinner("加载问题看板..."):
        render_problem_board_panel()
