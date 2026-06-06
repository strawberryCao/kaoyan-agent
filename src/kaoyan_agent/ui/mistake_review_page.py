import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.mistake_review_panel import render_mistake_review_panel


def render_mistake_review_page(settings: Settings) -> None:
    st.title("错题复习")
    render_mistake_review_panel(settings)
