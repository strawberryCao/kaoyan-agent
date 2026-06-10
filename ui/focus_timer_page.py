from datetime import timedelta

import streamlit as st

from schemas.focus_session import FocusTimerStatus
from workflows.focus_timer_workflow import FocusTimerWorkflow
from ui.focus_helpers import PENDING_FOCUS_TASK_ID_KEY, format_duration


def render_focus_timer_page() -> None:
    st.title("督学模式")
    st.caption("专注计时 · 暂停可恢复 · 结束后自动保存学习记录")

    workflow = FocusTimerWorkflow()
    pending_task_id = st.session_state.pop(PENDING_FOCUS_TASK_ID_KEY, None)
    if pending_task_id is not None:
        try:
            workflow.prepare_from_task(st.session_state, int(pending_task_id))
        except ValueError as exc:
            st.error(str(exc))

    state = workflow.get_timer_state(st.session_state)

    if not state.task_title:
        st.warning("请先在「今日作战台」选择一个任务，再点击「开始督学」。")
        if st.button("前往今日作战台", use_container_width=True):
            st.switch_page("pages/1_今日作战台.py")
        return

    elapsed_seconds = workflow.get_elapsed_seconds(state)
    remaining_seconds = workflow.get_remaining_seconds(state)
    planned_seconds = state.planned_minutes * 60

    col_task, col_plan = st.columns(2)
    with col_task:
        st.metric("当前任务", state.task_title)
    with col_plan:
        st.metric("计划时长", f"{state.planned_minutes} 分钟")

    status_labels = {
        FocusTimerStatus.IDLE: "待开始",
        FocusTimerStatus.RUNNING: "专注中",
        FocusTimerStatus.PAUSED: "已暂停",
        FocusTimerStatus.FINISHED: "已结束",
    }

    countdown_col, progress_col = st.columns([1, 1])
    with countdown_col:
        st.markdown("### 倒计时")
        st.markdown(
            f"<h1 style='text-align:center;font-size:3rem;margin:0;'>"
            f"{format_duration(remaining_seconds)}</h1>",
            unsafe_allow_html=True,
        )
    with progress_col:
        st.markdown("### 进度")
        progress = min(elapsed_seconds / planned_seconds, 1.0) if planned_seconds else 0
        st.progress(progress, text=f"已专注 {format_duration(elapsed_seconds)}")
        st.write(f"状态：**{status_labels[state.status]}**")
        st.write(f"暂停次数：**{state.pause_count}**")

    if state.status == FocusTimerStatus.RUNNING:
        _auto_refresh_countdown(workflow)

    st.divider()
    _render_controls(workflow, state)

    if state.status == FocusTimerStatus.FINISHED:
        st.success("本次督学已结束，记录已保存。可在「专注统计」查看。")


def _auto_refresh_countdown(workflow: FocusTimerWorkflow) -> None:
    @st.fragment(run_every=timedelta(seconds=1))
    def _tick():
        state = workflow.get_timer_state(st.session_state)
        if state.status != FocusTimerStatus.RUNNING:
            return
        remaining = workflow.get_remaining_seconds(state)
        elapsed = workflow.get_elapsed_seconds(state)
        st.caption(
            f"实时更新 · 剩余 {format_duration(remaining)} · "
            f"已专注 {format_duration(elapsed)}"
        )

    _tick()


def _render_controls(workflow: FocusTimerWorkflow, state) -> None:
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        start_disabled = state.status != FocusTimerStatus.IDLE
        if st.button(
            "开始",
            use_container_width=True,
            type="primary",
            disabled=start_disabled,
        ):
            try:
                workflow.start_timer(st.session_state)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    with col2:
        if st.button(
            "暂停",
            use_container_width=True,
            disabled=state.status != FocusTimerStatus.RUNNING,
        ):
            try:
                workflow.pause_timer(st.session_state)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    with col3:
        if st.button(
            "继续",
            use_container_width=True,
            disabled=state.status != FocusTimerStatus.PAUSED,
        ):
            try:
                workflow.resume_timer(st.session_state)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    with col4:
        end_disabled = state.status in {
            FocusTimerStatus.IDLE,
            FocusTimerStatus.FINISHED,
        }
        if st.button(
            "结束",
            use_container_width=True,
            disabled=end_disabled,
        ):
            st.session_state["show_focus_finish_form"] = True

    if st.session_state.get("show_focus_finish_form") and state.status not in {
        FocusTimerStatus.IDLE,
        FocusTimerStatus.FINISHED,
    }:
        with st.form("finish_focus_form"):
            reflection = st.text_area(
                "学习心得（可选）",
                placeholder="写下本次专注的收获、卡点或下一步计划…",
                height=100,
            )
            submitted = st.form_submit_button("确认结束并保存", type="primary")
            if submitted:
                try:
                    record = workflow.end_timer(
                        st.session_state,
                        reflection=reflection,
                    )
                    st.session_state.pop("show_focus_finish_form", None)
                    st.success(
                        f"已保存：实际专注 {record.actual_minutes} 分钟，"
                        f"{'完成计划' if record.completed else '未完成计划'}"
                    )
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    if state.status == FocusTimerStatus.FINISHED:
        if st.button("开始新的督学", use_container_width=True):
            workflow.reset_timer(st.session_state)
            st.session_state.pop("show_focus_finish_form", None)
            st.switch_page("pages/1_今日作战台.py")
