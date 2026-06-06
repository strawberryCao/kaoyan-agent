import streamlit as st

from kaoyan_agent.ui.components.problem_board_panel import render_problem_board_panel


def render_problem_board_page() -> None:
    st.title("问题板")
    render_problem_board_panel()
