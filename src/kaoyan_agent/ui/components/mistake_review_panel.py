import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.agents.practice_review import MISTAKE_REASON_LABELS
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


MASTERY_STATUS_LABELS = {
    "unmastered": "未掌握",
    "reviewing": "复习中",
    "mastered": "已掌握",
}


def render_mistake_review_panel(settings: Settings) -> None:
    workspace = WorkspaceWorkflow()

    with st.form("mistake_card_form"):
        subject = st.text_input("科目")
        chapter = st.text_input("章节或专题")
        question = st.text_area("原题或错误证据")
        user_reason = st.text_area("你认为的错误原因")
        submitted = st.form_submit_button("生成错题卡")

    if submitted and question.strip():
        with st.spinner("正在生成错题复习卡..."):
            card = PlanningWorkflow(settings).generate_and_save_practice_card(
                subject=subject,
                chapter=chapter,
                question=question,
                user_reason=user_reason,
            )
        st.success(f"错题卡已创建：#{card['id']}")
        st.json(card)

    cards = workspace.list_mistake_cards(limit=100)
    if cards:
        st.markdown("**错题池**")
        st.dataframe(cards, use_container_width=True)
        card_options = {f"#{card['id']} {card.get('chapter', '')}": int(card["id"]) for card in cards}
        selected_card = st.selectbox("选择错题卡", list(card_options.keys()), key="mistake_card")
        selected_label = st.selectbox("掌握状态", list(MASTERY_STATUS_LABELS.values()), key="mistake_status")
        status_by_label = {label: value for value, label in MASTERY_STATUS_LABELS.items()}
        if st.button("更新掌握状态", key="mistake_update"):
            workspace.update_mistake_status(card_options[selected_card], status_by_label[selected_label])
            st.success("掌握状态已更新。")
            st.rerun()
    else:
        st.info("还没有错题卡。")

    counts = workspace.mistake_reason_counts()
    if counts:
        labelled_counts = [
            {
                **item,
                "label": MISTAKE_REASON_LABELS.get(
                    item.get("mistake_reason", ""),
                    item.get("mistake_reason", ""),
                ),
            }
            for item in counts
        ]
        st.markdown("**错误原因分布**")
        st.dataframe(labelled_counts, use_container_width=True)
