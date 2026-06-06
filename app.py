from pathlib import Path
import sys

import streamlit as st


SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from kaoyan_agent.core.settings import get_settings
from kaoyan_agent.db import init_db
from kaoyan_agent.repositories.conversation_repository import ChatRepository
from kaoyan_agent.ui.chat_page import render_chat_page
from kaoyan_agent.ui.fortune_page import render_fortune_page
from kaoyan_agent.ui.mistake_review_page import render_mistake_review_page
from kaoyan_agent.ui.nightly_review_page import render_nightly_page
from kaoyan_agent.ui.problem_board_page import render_problem_board_page
from kaoyan_agent.ui.score_trend_page import render_score_trend_page
from kaoyan_agent.ui.settings_page import render_settings_page
from kaoyan_agent.ui.supervision_page import render_supervision_page
from kaoyan_agent.ui.task_page import render_task_page


VIEW_LABELS = {
    "tasks": "今日任务 / 学习规划",
    "supervision": "督学模式",
    "mistake_review": "错题复习",
    "score_trend": "成绩趋势",
    "nightly_review": "晚间回顾",
    "problem_board": "问题板",
    "fortune": "运势签",
    "settings": "设置",
}


def set_main_view(view: str) -> None:
    st.session_state.current_main_view = view


def ensure_navigation_state() -> None:
    st.session_state.setdefault("current_main_view", "chat")
    st.session_state.setdefault("current_chat_session_id", None)


def render_nav_button(label: str, view: str) -> None:
    if st.button(label, key=f"nav_{view}", use_container_width=True):
        set_main_view(view)
        st.rerun()


def render_sidebar(settings, chat_repository: ChatRepository) -> None:
    st.title("Kaoyan Agent")

    if st.button("+ 新建对话", key="new_chat_session", use_container_width=True):
        session_id = chat_repository.create_session()
        st.session_state.current_chat_session_id = session_id
        st.session_state.current_main_view = "chat"
        st.rerun()

    st.divider()
    st.subheader("常用功能")
    render_nav_button("今日任务 / 学习规划", "tasks")
    render_nav_button("督学模式", "supervision")
    render_nav_button("错题复习", "mistake_review")
    render_nav_button("成绩趋势", "score_trend")

    st.divider()
    st.subheader("最近会话")
    sessions = chat_repository.list_sessions(limit=20)
    if sessions:
        for session in sessions:
            label = session["title"] or chat_repository.default_session_title
            if session["id"] == st.session_state.get("current_chat_session_id"):
                label = f"* {label}"
            if st.button(label, key=f"chat_session_{session['id']}", use_container_width=True):
                st.session_state.current_chat_session_id = int(session["id"])
                st.session_state.current_main_view = "chat"
                st.rerun()
    else:
        st.caption("暂无会话")

    st.divider()
    st.subheader("Agent 诊断")
    render_nav_button("晚间回顾", "nightly_review")
    render_nav_button("问题板", "problem_board")

    st.divider()
    st.subheader("轻量激励")
    render_nav_button("运势签", "fortune")

    st.divider()
    render_nav_button("设置", "settings")
    st.caption(f"Model: {settings.llm_model}")
    st.caption(f"Database: {settings.database_path}")


def main() -> None:
    st.set_page_config(page_title="Kaoyan Problem Discovery Agent", layout="wide")
    settings = get_settings()
    init_db()
    ensure_navigation_state()

    chat_repository = ChatRepository()
    with st.sidebar:
        render_sidebar(settings, chat_repository)

    current_view = st.session_state.get("current_main_view", "chat")
    if current_view == "tasks":
        render_task_page(settings)
    elif current_view == "supervision":
        render_supervision_page()
    elif current_view == "mistake_review":
        render_mistake_review_page(settings)
    elif current_view == "score_trend":
        render_score_trend_page(settings)
    elif current_view == "nightly_review":
        render_nightly_page(settings)
    elif current_view == "problem_board":
        render_problem_board_page()
    elif current_view == "fortune":
        render_fortune_page(settings)
    elif current_view == "settings":
        render_settings_page(settings)
    else:
        render_chat_page(
            settings=settings,
            session_id=st.session_state.get("current_chat_session_id"),
        )


if __name__ == "__main__":
    main()
