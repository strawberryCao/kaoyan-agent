import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


def render_score_trend_panel(settings: Settings) -> None:
    workspace = WorkspaceWorkflow()

    with st.form("score_record"):
        subject = st.text_input("科目")
        score = st.number_input("分数", min_value=0.0, value=0.0)
        full_score = st.number_input("满分", min_value=1.0, value=100.0)
        exam_type = st.text_input("考试类型", value="练习")
        exam_date = st.date_input("考试日期").isoformat()
        note = st.text_area("备注")
        submitted = st.form_submit_button("保存成绩")
    if submitted and subject.strip():
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

    records = workspace.list_score_records(limit=50)
    if records:
        st.dataframe(records, use_container_width=True)
        chart_rows = [
            {
                "exam_date": record.get("exam_date"),
                "score_rate": round(
                    float(record.get("score") or 0)
                    / max(float(record.get("full_score") or 1), 1)
                    * 100,
                    2,
                ),
            }
            for record in reversed(records)
        ]
        st.line_chart(chart_rows, x="exam_date", y="score_rate")
    else:
        st.info("还没有成绩记录。")
