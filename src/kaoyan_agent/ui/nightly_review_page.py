import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import render_page_header
from kaoyan_agent.ui.components.nightly_review_panel import render_nightly_review_panel


def render_nightly_page(settings: Settings) -> None:
    render_page_header(
        "晚间回顾",
        "把当天原始证据转成可验证的问题、记忆和下一步干预。",
    )

    with st.spinner("加载晚间回顾..."):
        render_nightly_review_panel(settings)
