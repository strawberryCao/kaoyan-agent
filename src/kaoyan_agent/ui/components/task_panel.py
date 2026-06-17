import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import (
    inject_global_styles,
    render_empty_state,
    render_metric_card,
    render_section_title,
)
from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.ui.view_models import to_task_view_model
from kaoyan_agent.workflows.focus import FocusWorkflow
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow

TASK_STATUS_LABELS = {
    "todo": "待开始",
    "doing": "进行中",
    "done": "已完成",
}


def render_task_panel(settings: Settings) -> None:
    inject_global_styles()
    today = local_today()
    workspace = WorkspaceWorkflow()
    focus_workflow = FocusWorkflow()
    task_vms = [
        to_task_view_model(task, date_label=today)
        for task in workspace.list_tasks(today=today, limit=100)
    ]
    focus_stats = focus_workflow.get_stats()

    done_count = sum(1 for task in task_vms if task["status"] == "done")
    total_count = len(task_vms)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        render_metric_card("今日任务", total_count)
    with col_b:
        render_metric_card("已完成", done_count)
    with col_c:
        render_metric_card("今日专注分钟", focus_stats.get("today_focus_minutes", 0))

    render_next_step(task_vms)

    tab_today, tab_add, tab_history = st.tabs(["今日任务", "添加任务", "历史"])
    with tab_today:
        render_today_tasks(task_vms, workspace, focus_workflow)
        with st.expander("更新任务状态", expanded=False):
            render_update_status_form(task_vms, workspace)
    with tab_add:
        st.caption("需要添加任务时再打开表单，避免首屏被表单占满。")
        render_add_task_entry(settings, today)
    with tab_history:
        render_task_history(workspace)


def render_add_task_entry(settings: Settings, today: str) -> None:
    if hasattr(st, "dialog"):

        @st.dialog("添加今日任务")
        def add_task_dialog() -> None:
            render_create_task_form(settings, today)

        if st.button("添加任务", type="primary", key="task_add_dialog_open"):
            add_task_dialog()
    else:
        with st.expander("添加任务", expanded=False):
            render_create_task_form(settings, today)


def render_next_step(task_vms: list[dict]) -> None:
    render_section_title("推荐下一步")
    next_task = next(
        (task for task in task_vms if task["status"] in {"doing", "todo"}), None
    )
    if not next_task:
        render_empty_state(
            "今天还没有待执行任务",
            "可以从聊天里直接说：帮我创建一个 25 分钟数学任务。",
        )
        return

    # 合并为单个 st.html
    html = '<div class="kaoyan-card">'
    html += f'<div class="kaoyan-card-title">{next_task["title"]}</div>'
    html += (
        "<div>"
        f'<span class="kaoyan-badge">{next_task["status_label"]}</span>'
        f'<span class="kaoyan-badge">{next_task["subject"]}</span>'
        f'<span class="kaoyan-badge">{next_task["minutes"]} 分钟</span>'
        "</div>"
    )
    html += '<p style="font-size: 0.9rem; color: #888; margin: 4px 0;">建议先完成一个明确的小任务，再决定是否加码。</p>'
    html += "</div>"
    st.html(html)


def render_today_tasks(
    task_vms: list[dict],
    workspace: WorkspaceWorkflow,
    focus_workflow: FocusWorkflow,
) -> None:
    render_section_title("今日任务")
    if not task_vms:
        st.info("暂无今日任务。")
        return

    for task in task_vms:
        # 卡片开标签
        st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)

        # 合并静态内容（标题、标签）为单个 st.html
        html = f'<div class="kaoyan-card-title">{task["title"]}</div>'
        html += (
            "<div>"
            f'<span class="kaoyan-badge">{task["status_label"]}</span>'
            f'<span class="kaoyan-badge">{task["subject"]}</span>'
            f'<span class="kaoyan-badge">{task["minutes"]} 分钟</span>'
            f'<span class="kaoyan-badge">{task["source_label"]}</span>'
            "</div>"
        )
        st.html(html)

        # 交互按钮（保留原生组件）
        col_start, col_done = st.columns(2)
        if col_start.button("开始专注", key=f"task_focus_{task['raw_id']}"):
            result = focus_workflow.start_timer_for_task(
                task_id=task["raw_id"],
                task_title=task["title"],
                subject=task["subject"] if task["subject"] != "未指定" else "",
                planned_minutes=task["minutes"],
            )
            if result.get("status") == "started":
                st.success("已开始番茄钟，请到「督学模式」查看。")
            else:
                st.warning("当前已有番茄钟，请先到「督学模式」处理。")
            st.rerun()
        if task["status"] != "done" and col_done.button(
            "标记完成", key=f"task_done_{task['raw_id']}"
        ):
            workspace.update_task_status(task["raw_id"], "done")
            st.success("任务已标记完成。")
            st.rerun()

        # 卡片闭标签
        st.markdown("</div>", unsafe_allow_html=True)


def render_create_task_form(settings: Settings, today: str) -> None:
    with st.form("task_add"):
        title = st.text_input("任务标题")
        subject = st.text_input("科目")
        estimated_minutes = st.number_input(
            "预计分钟",
            min_value=1,
            max_value=300,
            value=25,
            step=5,
        )
        submitted = st.form_submit_button("创建任务")
    if submitted:
        if not title.strip():
            st.warning("任务标题不能为空。")
        else:
            PlanningWorkflow(settings).create_task(
                title=title.strip(),
                subject=subject.strip(),
                estimated_minutes=int(estimated_minutes),
                source="manual",
                scheduled_date=today,
            )
            st.success("任务已创建。")
            st.rerun()


def render_update_status_form(
    task_vms: list[dict], workspace: WorkspaceWorkflow
) -> None:
    if not task_vms:
        st.caption("暂无可更新任务。")
        return

    task_options = {
        f"{task['title']}（{task['minutes']} 分钟）": task["raw_id"]
        for task in task_vms
    }
    selected_task = st.selectbox(
        "选择任务", list(task_options.keys()), key="task_select"
    )
    selected_label = st.selectbox(
        "新状态",
        list(TASK_STATUS_LABELS.values()),
        key="task_status",
    )
    status_by_label = {label: value for value, label in TASK_STATUS_LABELS.items()}
    if st.button("更新状态", key="task_update"):
        workspace.update_task_status(
            task_options[selected_task], status_by_label[selected_label]
        )
        st.success("任务状态已更新。")
        st.rerun()


def render_task_history(workspace: WorkspaceWorkflow) -> None:
    tasks = workspace.list_tasks(today=None, limit=30)
    if not tasks:
        st.info("暂无历史任务。")
        return
    for task in tasks:
        vm = to_task_view_model(task)
        # 合并为单个 st.html
        html = '<div class="kaoyan-card">'
        html += f'<div class="kaoyan-card-title">{vm["title"]}</div>'
        html += (
            "<div>"
            f'<span class="kaoyan-badge">{vm["status_label"]}</span>'
            f'<span class="kaoyan-badge">{vm["subject"]}</span>'
            f'<span class="kaoyan-badge">{vm["minutes"]} 分钟</span>'
            "</div>"
        )
        date_str = str(task.get("scheduled_date") or task.get("created_at") or "")
        html += (
            f'<p style="font-size: 0.9rem; color: #888; margin: 4px 0;">{date_str}</p>'
        )
        html += "</div>"
        st.html(html)
