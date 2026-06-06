import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.score_trend_panel import render_score_trend_panel


def render_score_trend_page(settings: Settings) -> None:
    st.title("成绩趋势")
    render_score_trend_panel(settings)
