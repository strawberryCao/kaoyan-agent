import streamlit as st

from kaoyan_agent.ui.components.common import (
    install_card_styles,
    render_json_debug_expander,
    render_metric_card,
    render_section_title,
)
from kaoyan_agent.ui.view_models import to_problem_view_model
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow

PROBLEM_STATUS_LABELS = {
    "open": "打开",
    "watching": "观察中",
    "resolved": "已解决",
    "ignored": "已忽略",
    "archived": "已归档",
}


def render_problem_board_panel() -> None:
    install_card_styles()
    workspace = WorkspaceWorkflow()
    open_problems = workspace.list_problems_by_statuses(["open", "watching"], limit=100)
    resolved_problems = workspace.list_problems_by_statuses(
        ["resolved", "ignored", "archived"], limit=80
    )

    high_severity = sum(
        1 for problem in open_problems if int(problem.get("severity") or 1) >= 4
    )
    col_open, col_high, col_resolved = st.columns(3)
    with col_open:
        render_metric_card("开放问题", len(open_problems))
    with col_high:
        render_metric_card("高严重度", high_severity)
    with col_resolved:
        render_metric_card("已处理", len(resolved_problems))

    tab_open, tab_resolved, tab_evidence = st.tabs(["开放问题", "已解决", "证据详情"])
    with tab_open:
        render_problem_list(open_problems, workspace, allow_update=True)
    with tab_resolved:
        render_problem_list(resolved_problems, workspace, allow_update=False)
    with tab_evidence:
        render_evidence_details(open_problems + resolved_problems)


def render_problem_list(
    problems: list[dict],
    workspace: WorkspaceWorkflow,
    allow_update: bool,
) -> None:
    if not problems:
        st.info("暂无问题。收集对话证据后运行 Nightly Review，会在这里沉淀可干预问题。")
        return
    for problem in problems:
        render_problem_card(problem)
    if allow_update:
        with st.expander("更新问题状态", expanded=False):
            render_status_update_form(problems, workspace)


def render_status_update_form(
    problems: list[dict], workspace: WorkspaceWorkflow
) -> None:
    problem_options = {
        f"{problem.get('description', '')[:36] or '未命名问题'} / #{problem['id']}": int(
            problem["id"]
        )
        for problem in problems
    }
    selected_problem = st.selectbox(
        "选择问题", list(problem_options.keys()), key="problem_select"
    )
    selected_label = st.selectbox(
        "问题状态",
        list(PROBLEM_STATUS_LABELS.values()),
        key="problem_status",
    )
    status_by_label = {label: value for value, label in PROBLEM_STATUS_LABELS.items()}
    if st.button("更新问题状态", key="problem_update"):
        if workspace.update_problem_status(
            problem_options[selected_problem], status_by_label[selected_label]
        ):
            st.success("问题状态已更新。")
            st.rerun()
        st.warning("未找到该问题。")


def render_problem_card(problem: dict) -> None:
    """使用 st.html 一次性渲染问题卡片，避免多个 st.markdown 碎片。"""
    vm = to_problem_view_model(problem)

    # 构建完整的卡片 HTML
    html = '<div class="kaoyan-card">'
    html += f'<div class="kaoyan-card-title">{vm["description"]}</div>'

    # 状态标签区域
    html += (
        "<div>"
        f'<span class="kaoyan-badge">{vm["problem_type_label"]}</span>'
        f'<span class="kaoyan-badge">{vm["subject"]}</span>'
        f'<span class="kaoyan-badge">严重度 {vm["severity_label"]}</span>'
        f'<span class="kaoyan-badge">置信度 {vm["confidence_label"]}</span>'
        f'<span class="kaoyan-badge">{vm["status_label"]}</span>'
        "</div>"
    )

    if vm["root_cause"]:
        html += f'<p><strong>可能根因：</strong>{vm["root_cause"]}</p>'
    if vm["suggested_action"]:
        html += f'<p><strong>建议行动：</strong>{vm["suggested_action"]}</p>'

    html += "</div>"  # 关闭卡片

    # 一次性渲染所有 HTML
    with st.container(border=True):
        st.html(html)


def render_evidence_details(problems: list[dict]) -> None:
    render_section_title("证据详情")
    if not problems:
        st.info("暂无可展示证据。")
        return
    for problem in problems[:30]:
        vm = to_problem_view_model(problem)
        with st.expander(vm["description"], expanded=False):
            st.caption(vm["evidence_summary"])
            render_json_debug_expander(
                "证据引用",
                {
                    "evidence": problem.get("evidence") or [],
                    "evidence_refs": problem.get("evidence_refs") or [],
                },
            )
