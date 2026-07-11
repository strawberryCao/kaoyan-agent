import html
import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import (
    install_card_styles,
    mistake_reason_label,
    render_json_debug_expander,
    render_section_title,
)
from kaoyan_agent.ui.view_models import to_review_card_view_model
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow

MASTERY_STATUS_LABELS = {
    "unmastered": "未掌握",
    "reviewing": "复习中",
    "mastered": "已掌握",
}


def render_mistake_review_panel(settings: Settings) -> None:
    install_card_styles()
    workspace = WorkspaceWorkflow()
    cards = workspace.list_mistake_cards(limit=100)

    tab_generate, tab_pool, tab_queue = st.tabs(["生成错题卡", "错题池", "复习队列"])
    with tab_generate:
        render_generate_tab(settings)
    with tab_pool:
        render_card_pool(cards)
    with tab_queue:
        render_review_queue(cards, workspace)


def render_generate_tab(settings: Settings) -> None:
    render_section_title(
        "生成错题卡", "只在有题目或错误证据时生成，避免沉淀低质量错题。"
    )
    if hasattr(st, "dialog"):

        @st.dialog("生成错题卡")
        def generate_dialog() -> None:
            render_generate_form(settings)

        if st.button("填写错题信息", type="primary", key="mistake_generate_dialog"):
            generate_dialog()
    else:
        with st.expander("生成错题卡", expanded=True):
            render_generate_form(settings)

    card = st.session_state.get("latest_generated_mistake_card")
    if card:
        render_review_card(card)
        render_json_debug_expander(
            "开发调试信息",
            (
                {"generation_error": card.get("generation_error")}
                if card.get("generation_error")
                else {}
            ),
        )


def render_generate_form(settings: Settings) -> None:
    with st.form("mistake_card_form"):
        subject = st.text_input("科目")
        chapter = st.text_input("章节或专题")
        question = st.text_area("原题或错误证据")
        user_reason = st.text_area("你认为的错误原因")
        submitted = st.form_submit_button("生成错题卡")

    if submitted:
        if not question.strip():
            st.warning("请先补充题目或错误证据。")
        else:
            with st.spinner("正在生成错题复盘卡..."):
                card = PlanningWorkflow(settings).generate_and_save_practice_card(
                    subject=subject,
                    chapter=chapter,
                    question=question,
                    user_reason=user_reason,
                )
            if card.get("generation_error"):
                st.info("已使用备用错题卡生成。")
            st.session_state.latest_generated_mistake_card = card
            st.success("错题卡已创建。")
            st.rerun()


def render_card_pool(cards: list[dict]) -> None:
    render_section_title("错题池")
    if not cards:
        st.info("还没有错题卡。")
        return
    for card in cards[:30]:
        render_review_card(card, compact=True)


def render_review_queue(cards: list[dict], workspace: WorkspaceWorkflow) -> None:
    render_section_title("复习队列")
    if not cards:
        st.info("暂无可复习错题。")
        return

    queue = [card for card in cards if card.get("mastery_status") != "mastered"]
    for card in queue[:12]:
        render_review_card(card, compact=True)

    with st.expander("更新掌握状态", expanded=False):
        card_options = {
            f"{card.get('subject') or '未指定'} / {card.get('chapter') or '未指定'} / #{card['id']}": int(
                card["id"]
            )
            for card in cards
        }
        selected_card = st.selectbox(
            "选择错题卡", list(card_options.keys()), key="mistake_card"
        )
        selected_label = st.selectbox(
            "掌握状态",
            list(MASTERY_STATUS_LABELS.values()),
            key="mistake_status",
        )
        status_by_label = {
            label: value for value, label in MASTERY_STATUS_LABELS.items()
        }
        if st.button("更新掌握状态", key="mistake_update"):
            workspace.update_mistake_status(
                card_options[selected_card], status_by_label[selected_label]
            )
            st.success("掌握状态已更新。")
            st.rerun()

    counts = workspace.mistake_reason_counts()
    if counts:
        with st.expander("错因分布", expanded=False):
            for item in counts:
                st.caption(
                    f"{mistake_reason_label(item.get('mistake_reason', 'unknown'))}：{item.get('count', 0)} 张"
                )


def render_review_card(card: dict, compact: bool = False) -> None:
    vm = to_review_card_view_model(card)
    # Escape all text fields
    subject = html.escape(vm.get("subject", ""))
    chapter = html.escape(vm.get("chapter", ""))
    question = html.escape(vm.get("question", ""))
    mistake_reason_label_esc = html.escape(vm.get("mistake_reason_label", ""))
    priority_label_esc = html.escape(vm.get("priority_label", ""))
    mastery_status_label_esc = html.escape(vm.get("mastery_status_label", ""))
    knowledge_points = html.escape(vm.get("knowledge_points", ""))
    analysis = html.escape(vm.get("analysis", ""))

    # Build HTML
    title = f"{subject} / {chapter}"
    if compact:
        question_short = html.escape(shorten(vm.get("question", "")))
        content = f"""
        <div class="kaoyan-card">
            <div class="kaoyan-card-title">{title}</div>
            <div><strong>题目/证据：</strong> {question_short}</div>
            <div><strong>错因：</strong> {mistake_reason_label_esc}</div>
            <div><strong>优先级：</strong> {priority_label_esc}</div>
            <div><strong>掌握状态：</strong> {mastery_status_label_esc}</div>
        </div>
        """
    else:
        content = f"""
        <div class="kaoyan-card">
            <div class="kaoyan-card-title">{title}</div>
            <div><strong>知识点：</strong> {knowledge_points}</div>
            <div><strong>错误原因：</strong> {mistake_reason_label_esc}</div>
            <div><strong>分析：</strong> {analysis}</div>
            <div><strong>复习优先级：</strong> {priority_label_esc}</div>
        </div>
        """
    st.html(content)


def shorten(value: str, limit: int = 90) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."
