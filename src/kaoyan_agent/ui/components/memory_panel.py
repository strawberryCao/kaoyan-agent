import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.workflows.settings_workflow import SettingsWorkflow


def render_memory_panel(settings: Settings) -> None:
    st.subheader("记忆库")
    limit = st.slider("显示数量", min_value=10, max_value=200, value=100, step=10, key="memory_limit")
    data = SettingsWorkflow().load_settings(settings=settings, memory_limit=limit)
    memories = data.get("memories") or []
    if memories:
        st.dataframe(memories, use_container_width=True)
    else:
        st.info("还没有长期记忆。晚间回顾成功解析后会写入这里。")
