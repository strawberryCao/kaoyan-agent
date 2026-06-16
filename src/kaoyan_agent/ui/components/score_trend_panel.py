import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import (
    inject_global_styles,
    render_empty_state,
    render_metric_card,
    render_section_title,
)
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


def render_score_trend_panel(settings: Settings) -> None:
    inject_global_styles()
    workspace = WorkspaceWorkflow()
    records = workspace.list_score_records(limit=50)

    if records:
        latest = records[0]
        scores = [float(record.get("score") or 0) for record in records]
        average = round(sum(scores) / len(scores), 1)
        col_latest, col_avg, col_count = st.columns(3)
        with col_latest:
            render_metric_card("最近一次分数", f"{latest.get('score', 0)} / {latest.get('full_score', 100)}")
        with col_avg:
            render_metric_card("平均分", average)
        with col_count:
            render_metric_card("记录次数", len(records))

        chart_rows = [
            {
                "考试日期": record.get("exam_date"),
                "得分率": round(
                    float(record.get("score") or 0)
                    / max(float(record.get("full_score") or 1), 1)
                    * 100,
                    2,
                ),
            }
            for record in reversed(records)
        ]
        st.line_chart(chart_rows, x="考试日期", y="得分率")
    else:
        render_empty_state("还没有成绩记录", "添加一次练习或模考成绩后，这里会显示趋势。")

    with st.expander("添加成绩记录", expanded=False):
        render_score_form(settings)

    with st.expander("历史记录", expanded=False):
        if records:
            for record in records:
                render_score_record(record)
        else:
            st.caption("暂无历史记录。")


def render_score_form(settings: Settings) -> None:
    with st.form("score_record"):
        subject = st.text_input("科目")
        score = st.number_input("分数", min_value=0.0, value=0.0)
        full_score = st.number_input("满分", min_value=1.0, value=100.0)
        exam_type = st.text_input("考试类型", value="练习")
        exam_date = st.date_input("考试日期").isoformat()
        note = st.text_area("备注")
        submitted = st.form_submit_button("保存成绩")
    if submitted:
        if not subject.strip():
            st.warning("科目不能为空。")
            return
        PlanningWorkflow(settings).record_score(
            subject=subject,
            score=float(score),
            full_score=float(full_score),
            exam_type=exam_type,
            exam_date=exam_date,
            note=note,
        )
        st.success("成绩已保存。")
        st.rerun()


def render_score_record(record: dict) -> None:
    st.markdown('<div class="kaoyan-card">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="kaoyan-card-title">{record.get("subject") or "未指定科目"}：'
        f'{record.get("score", 0)} / {record.get("full_score", 100)}</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"日期：{record.get('exam_date', '')} / 类型：{record.get('exam_type', '')}")
    if record.get("note"):
        st.markdown(f"**备注：** {record.get('note')}")
    st.markdown("</div>", unsafe_allow_html=True)
