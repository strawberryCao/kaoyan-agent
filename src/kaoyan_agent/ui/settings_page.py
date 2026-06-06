import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.memory_panel import render_memory_panel
from kaoyan_agent.workflows.settings_workflow import SettingsWorkflow


def render_settings_page(settings: Settings) -> None:
    st.title("设置")
    render_memory_panel(settings)

    data = SettingsWorkflow().load_settings(settings=settings, memory_limit=1)
    st.divider()
    st.subheader("模型信息")
    st.write(f"Model: `{data['model']}`")
    st.write(f"Database: `{data['database_path']}`")
