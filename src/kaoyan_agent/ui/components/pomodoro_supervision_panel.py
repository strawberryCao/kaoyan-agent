import streamlit as st

from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.workflows.focus import FocusWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


SUPERVISION_STATUSES = ["completed", "interrupted", "failed"]
STATE_LABELS = ["focused", "away", "distracted", "blocked", "unknown"]


def render_pomodoro_supervision_panel() -> None:
    tasks = WorkspaceWorkflow().list_tasks(today=local_today(), limit=100)
    task_options = {"不关联任务": None}
    for task in tasks:
        task_options[f"#{task['id']} {task.get('title', '')}"] = int(task["id"])

    selected_task = st.selectbox("关联任务", list(task_options.keys()), key="supervision_task")
    planned_minutes = st.number_input(
        "计划学习分钟数",
        min_value=1,
        max_value=240,
        value=25,
        step=5,
        key="supervision_minutes",
    )
    workflow = FocusWorkflow()
    if st.button("开始番茄钟", type="primary", key="supervision_start"):
        session_id = workflow.start_focus_session(
            task_id=task_options[selected_task],
            planned_minutes=int(planned_minutes),
        )
        st.session_state.current_supervision_session_id = session_id
        st.success(f"番茄钟已开始：#{session_id}")

    current_id = st.session_state.get("current_supervision_session_id")
    if not current_id:
        st.info("开始后可记录中断、状态和完成情况。")
        return

    st.markdown(f"**当前番茄钟 #{current_id}**")
    selected_state = st.selectbox("学习状态记录", STATE_LABELS, key="supervision_state")
    confidence = st.slider("置信度", min_value=0.0, max_value=1.0, value=0.7, key="supervision_confidence")
    explanation = st.text_input("简短说明", key="supervision_explanation")
    if st.button("记录状态", key="supervision_record_state"):
        workflow.record_camera_state(
            focus_session_id=int(current_id),
            state_type=selected_state,
            confidence=float(confidence),
            explanation=explanation,
        )
        st.success("状态已记录。")

    actual_minutes = st.number_input(
        "实际学习分钟数",
        min_value=0,
        max_value=240,
        value=int(planned_minutes),
        step=5,
        key="supervision_actual",
    )
    pause_count = st.number_input("暂停次数", min_value=0, max_value=50, value=0, key="supervision_pause")
    completion_status = st.selectbox("完成情况", SUPERVISION_STATUSES, key="supervision_done")
    reflection = st.text_area("复盘备注", key="supervision_reflection")
    if st.button("结束番茄钟", key="supervision_finish"):
        workflow.finish_focus_session(
            focus_session_id=int(current_id),
            actual_minutes=int(actual_minutes),
            pause_count=int(pause_count),
            completion_status=completion_status,
            reflection=reflection,
        )
        st.session_state.pop("current_supervision_session_id", None)
        st.success("番茄钟已结束。")
        st.rerun()
