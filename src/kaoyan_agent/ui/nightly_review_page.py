import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.nightly_review_panel import render_nightly_review_panel


def render_nightly_page(settings: Settings) -> None:
    st.title("晚间回顾")
    render_nightly_review_panel(settings)
