import streamlit as st

from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


PROBLEM_STATUS_LABELS = {
    "open": "打开",
    "watching": "观察中",
    "resolved": "已解决",
    "ignored": "已忽略",
    "archived": "已归档",
}


def render_problem_board_panel() -> None:
    workspace = WorkspaceWorkflow()
    problems = workspace.list_open_problems()

    if not problems:
        st.info("暂无打开的问题。收集一段对话证据后运行晚间回顾。")
        return

    st.dataframe(problems, use_container_width=True)
    problem_options = {
        f"#{problem['id']} {problem.get('description', '')[:30]}": int(problem["id"])
        for problem in problems
    }
    selected_problem = st.selectbox("选择问题", list(problem_options.keys()), key="problem_select")
    selected_label = st.selectbox("问题状态", list(PROBLEM_STATUS_LABELS.values()), key="problem_status")
    status_by_label = {label: value for value, label in PROBLEM_STATUS_LABELS.items()}
    if st.button("更新问题状态", key="problem_update"):
        if workspace.update_problem_status(problem_options[selected_problem], status_by_label[selected_label]):
            st.success("问题状态已更新。")
            st.rerun()
        else:
            st.error("未找到该问题。")
