import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.fortune_card import render_fortune_card


def render_fortune_page(settings: Settings) -> None:
    st.title("运势签")
    render_fortune_card(settings)
