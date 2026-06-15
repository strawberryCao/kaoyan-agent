import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.review_panel import render_review_panel


def render_review_page(settings: Settings) -> None:
    st.title("📚 刷题复刷")
    render_review_panel(settings)
