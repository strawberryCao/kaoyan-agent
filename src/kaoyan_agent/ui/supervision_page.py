import streamlit as st

from kaoyan_agent.ui.components.common import render_page_header
from kaoyan_agent.ui.components.pomodoro_supervision_panel import (
    render_pomodoro_supervision_panel,
)


def render_supervision_page() -> None:
    render_page_header(
        "督学模式",
        "用番茄钟记录真实学习过程，必要时进行状态识别。",
    )
    render_pomodoro_supervision_panel()
