import streamlit as st

from kaoyan_agent.repositories.agent_trace import AgentTraceRepository
from kaoyan_agent.ui.components.common import (
    inject_global_styles,
    render_json_debug_expander,
    render_page_header,
    render_status_badge,
)


def render_agent_trace_page() -> None:
    inject_global_styles()
    render_page_header(
        "执行轨迹",
        "展示在线会话的工程执行步骤，不展示模型隐藏思维或完整提示词。",
        badge="Agent 诊断",
    )

    with st.spinner("加载执行轨迹..."):
        repository = AgentTraceRepository()
        col_status, col_limit = st.columns([1, 1])
        status_filter = col_status.selectbox(
            "状态过滤",
            [
                "全部",
                "ok",
                "running",
                "llm_request_error",
                "action_success",
                "action_warning",
            ],
            key="trace_status_filter",
        )
        limit = col_limit.number_input(
            "显示数量", min_value=5, max_value=100, value=30, step=5
        )
        filters = {}
        if status_filter != "全部":
            filters["status"] = status_filter
        runs = repository.list_recent_runs(limit=int(limit), filters=filters)
        if not runs:
            st.info("暂无在线会话执行轨迹。")
            return

        for run in runs:
            response = run.get("response") or {}
            structured = response.get("structured_data") or {}
            action_result = structured.get("action_result") or {}
            title = (
                f"Run #{run.get('id')} · {render_status_badge(run.get('parse_status', ''))} · "
                f"{run.get('created_at', '')}"
            )
            with st.expander(title, expanded=False):
                st.caption(
                    f"Session: {run.get('session_id') or '-'} / "
                    f"Assistant Message: {run.get('assistant_message_id') or '-'} / "
                    f"耗时：{int(run.get('duration_ms') or 0)} ms / "
                    f"动作：{action_result.get('action_type') or '无'}"
                )
                steps = repository.list_steps(int(run["id"]))
                for step in steps:
                    st.markdown(
                        f"**{int(step.get('step_order') or 0)}. {step.get('step_name')}** "
                        f"({step.get('step_type')} / {step.get('status')})"
                    )
                    if step.get("decision_summary"):
                        st.caption(step["decision_summary"])
                    if step.get("output_summary"):
                        st.write(step["output_summary"])
                    if step.get("error_message"):
                        st.caption("该步骤使用了备用路径或出现可恢复问题。")
                render_json_debug_expander(
                    "开发调试信息",
                    {
                        "run_id": run.get("id"),
                        "action_result": action_result,
                        "step_count": len(steps),
                    },
                )
