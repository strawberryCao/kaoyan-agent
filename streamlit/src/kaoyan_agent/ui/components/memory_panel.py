import html
import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import inject_global_styles, render_empty_state
from kaoyan_agent.workflows.settings_workflow import SettingsWorkflow


def render_memory_panel(settings: Settings) -> None:
    inject_global_styles()
    with st.expander("记忆库", expanded=False):
        limit = st.slider(
            "显示数量",
            min_value=10,
            max_value=200,
            value=50,
            step=10,
            key="memory_limit",
        )
        data = SettingsWorkflow().load_settings(settings=settings, memory_limit=limit)
        st.caption(
            f"Embedding: {data.get('embedding_provider')} / {data.get('embedding_model')}"
        )

        memories = data.get("memories") or []
        st.markdown("**长期记忆**")
        if memories:
            for memory in memories:
                render_memory_card(memory)
        else:
            render_empty_state(
                "还没有长期记忆",
                "晚间回顾成功解析并通过 Memory Gate 后，会在这里沉淀长期记忆。",
            )

        skills = data.get("skill_memories") or []
        st.markdown("**技能记忆**")
        if skills:
            for skill in skills:
                render_skill_card(skill)
        else:
            render_empty_state(
                "还没有技能记忆",
                "只有可复用、可验证的干预流程会沉淀为 Skill Memory。",
            )


def render_memory_card(memory: dict) -> None:
    memory_type = html.escape(str(memory.get("memory_type") or "记忆"))
    content = html.escape(str(memory.get("content") or ""))
    importance = memory.get("importance", 1)
    confidence = float(memory.get("confidence") or 0)
    st.html(f"""
        <div class="kaoyan-card">
            <strong>{memory_type}</strong>
            <div>{content}</div>
            <div style="font-size:0.85rem;color:var(--kaoyan-text-muted);">重要度：{importance} / 置信度：{confidence:.2f}</div>
        </div>
    """)


def render_skill_card(skill: dict) -> None:
    skill_name = html.escape(str(skill.get("skill_name") or "技能记忆"))
    description = html.escape(str(skill.get("description") or ""))
    confidence = float(skill.get("confidence") or 0)
    st.html(f"""
        <div class="kaoyan-card">
            <strong>{skill_name}</strong>
            <div>{description}</div>
            <div style="font-size:0.85rem;color:var(--kaoyan-text-muted);">置信度：{confidence:.2f}</div>
        </div>
    """)
