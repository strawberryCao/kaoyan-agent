import streamlit as st

from schemas.task import DailyTaskCreate, DailyTaskStatus
from workflows.daily_task_workflow import DailyTaskWorkflow
from workflows.focus_timer_workflow import FocusTimerWorkflow
from ui.focus_helpers import PENDING_FOCUS_TASK_ID_KEY


def render_battle_station_page() -> None:
    st.title("今日作战台")
    st.caption("选择今日任务，点击「开始督学」进入专注计时。")

    workflow = DailyTaskWorkflow()
    tasks = workflow.get_today_tasks(seed_demo=True)

    with st.expander("添加任务", expanded=not tasks):
        with st.form("add_daily_task_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                subject = st.text_input("科目", placeholder="例如：数学")
                task = st.text_input("任务内容", placeholder="例如：高数极限复习")
            with col2:
                estimated_minutes = st.number_input(
                    "计划时长（分钟）",
                    min_value=5,
                    max_value=180,
                    value=25,
                    step=5,
                )
                reason = st.text_input("原因/备注", placeholder="可选")
            submitted = st.form_submit_button("添加任务", use_container_width=True)
            if submitted:
                if not task.strip():
                    st.error("请填写任务内容")
                else:
                    workflow.add_task(
                        DailyTaskCreate(
                            subject=subject.strip(),
                            task=task.strip(),
                            reason=reason.strip(),
                            estimated_minutes=int(estimated_minutes),
                        )
                    )
                    st.success("任务已添加")
                    st.rerun()

    if not tasks:
        st.info("今天还没有任务，请先添加一个。")
        return

    st.subheader("今日任务")
    status_labels = {
        DailyTaskStatus.PENDING: "待开始",
        DailyTaskStatus.IN_PROGRESS: "进行中",
        DailyTaskStatus.DONE: "已完成",
    }

    for task in tasks:
        with st.container(border=True):
            col_info, col_action = st.columns([3, 1])
            with col_info:
                st.markdown(f"**{task.display_title}**")
                st.caption(
                    f"计划 {task.estimated_minutes} 分钟 · "
                    f"状态：{status_labels[task.status]}"
                )
                if task.reason:
                    st.write(task.reason)
            with col_action:
                if st.button(
                    "开始督学",
                    key=f"start_focus_{task.id}",
                    use_container_width=True,
                    type="primary",
                ):
                    timer_workflow = FocusTimerWorkflow()
                    timer_workflow.prepare_from_task(st.session_state, task.id)
                    st.session_state[PENDING_FOCUS_TASK_ID_KEY] = task.id
                    st.switch_page("pages/2_督学模式.py")
