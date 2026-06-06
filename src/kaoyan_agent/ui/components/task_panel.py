import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


TASK_STATUS_LABELS = {
    "todo": "待办",
    "doing": "进行中",
    "done": "已完成",
    "skipped": "跳过",
    "delayed": "延期",
}


def render_task_panel(settings: Settings) -> None:
    today = local_today()
    workspace = WorkspaceWorkflow()
    tasks = workspace.list_tasks(today=today, limit=100)

    done_count = sum(1 for task in tasks if task.get("status") == "done")
    total_count = len(tasks)
    completion_rate = 0 if total_count == 0 else round(done_count / total_count * 100, 1)
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("完成率", f"{completion_rate}%")
    col_b.metric("已完成", done_count)
    col_c.metric("未完成", total_count - done_count)

    if tasks:
        st.dataframe(tasks, use_container_width=True)
    else:
        st.info("今天还没有任务。")

    with st.form("task_add"):
        title = st.text_input("任务标题")
        subject = st.text_input("科目")
        estimated_minutes = st.number_input("预计分钟数", min_value=0, max_value=300, value=25, step=5)
        submitted = st.form_submit_button("创建任务")
    if submitted and title.strip():
        PlanningWorkflow(settings).create_task(
            title=title,
            subject=subject,
            estimated_minutes=int(estimated_minutes),
            source="manual",
            scheduled_date=today,
        )
        st.success("任务已创建。")
        st.rerun()

    if not tasks:
        return

    st.markdown("**更新任务状态**")
    task_options = {f"#{task['id']} {task.get('title', '')}": int(task["id"]) for task in tasks}
    selected_task = st.selectbox("选择任务", list(task_options.keys()), key="task_select")
    selected_label = st.selectbox("新状态", list(TASK_STATUS_LABELS.values()), key="task_status")
    status_by_label = {label: value for value, label in TASK_STATUS_LABELS.items()}
    if st.button("更新任务", key="task_update"):
        workspace.update_task_status(task_options[selected_task], status_by_label[selected_label])
        st.success("任务状态已更新。")
        st.rerun()
