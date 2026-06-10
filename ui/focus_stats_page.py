from datetime import datetime

import streamlit as st

from workflows.focus_timer_workflow import FocusTimerWorkflow
from ui.focus_helpers import format_duration


def render_focus_stats_page() -> None:
    st.title("专注统计")
    st.caption("查看督学记录与专注趋势，供每日复盘参考。")

    workflow = FocusTimerWorkflow()
    stats = workflow.get_stats()
    recent_sessions = workflow.list_recent_sessions(limit=15)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("今日专注", f"{stats.today_focus_minutes} 分钟")
    col2.metric("今日次数", stats.today_sessions)
    col3.metric("本周专注", f"{stats.week_focus_minutes} 分钟")
    col4.metric("完成率", f"{stats.completion_rate}%")

    st.divider()

    left, right = st.columns([1, 1])
    with left:
        st.subheader("近 7 日专注时长")
        if stats.daily_minutes:
            chart_data = {
                day: minutes for day, minutes in stats.daily_minutes.items()
            }
            st.bar_chart(chart_data)
        else:
            st.info("暂无数据，完成一次督学后会在这里显示。")

    with right:
        st.subheader("累计概览")
        st.write(f"- 总督学次数：**{stats.total_sessions}**")
        st.write(f"- 总专注时长：**{stats.total_focus_minutes} 分钟**")
        st.write(f"- 本周完成：**{stats.week_completed} / {stats.week_sessions}**")
        st.write(f"- 今日完成：**{stats.today_completed} / {stats.today_sessions}**")

    st.divider()
    st.subheader("最近督学记录")

    if not recent_sessions:
        st.info("还没有督学记录。去「今日作战台」选任务开始吧。")
        return

    for session in recent_sessions:
        with st.container(border=True):
            title = session.task_title
            if session.subject and session.subject not in title:
                title = f"{session.subject} · {title}"

            started = _format_time(session.started_at)
            ended = _format_time(session.ended_at) if session.ended_at else "-"
            completed_label = "已完成" if session.completed else "未完成"

            st.markdown(f"**{title}**")
            st.caption(
                f"{started} → {ended} · "
                f"计划 {session.planned_minutes} 分钟 · "
                f"实际 {session.actual_minutes} 分钟 · "
                f"暂停 {session.pause_count} 次 · {completed_label}"
            )
            if session.reflection:
                st.write(f"心得：{session.reflection}")


def _format_time(iso_text: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_text)
        return dt.strftime("%m-%d %H:%M")
    except ValueError:
        return iso_text
