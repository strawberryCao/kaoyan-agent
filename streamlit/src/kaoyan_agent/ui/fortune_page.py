import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import render_page_header
from kaoyan_agent.ui.components.fortune_card import render_fortune_card


def render_fortune_page(settings: Settings) -> None:
    render_page_header(
        "幸运卡",
        "低压力启动工具：给你一个小行动，而不是一堆计划。",
    )

    with st.spinner("加载幸运卡..."):
        render_fortune_card(settings)
