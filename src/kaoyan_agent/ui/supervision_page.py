import streamlit as st

from kaoyan_agent.ui.components.pomodoro_supervision_panel import (
    render_pomodoro_supervision_panel,
)


def render_supervision_page() -> None:
    st.title("督学模式")
    render_pomodoro_supervision_panel()
