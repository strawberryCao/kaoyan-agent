import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import render_page_header
from kaoyan_agent.ui.components.mistake_review_panel import render_mistake_review_panel


def render_mistake_review_page(settings: Settings) -> None:
    render_page_header(
        "错题复盘",
        "不是收集错题，而是找出你反复卡住的原因。",
    )

    with st.spinner("加载错题复盘..."):
        render_mistake_review_panel(settings)
