import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import render_page_header
from kaoyan_agent.ui.components.score_trend_panel import render_score_trend_panel


def render_score_trend_page(settings: Settings) -> None:
    render_page_header(
        "成绩趋势",
        "用简洁趋势看见分数变化，而不是堆叠原始记录。",
    )

    with st.spinner("加载成绩趋势..."):
        render_score_trend_panel(settings)
