from collections import Counter

import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.common import (
    inject_global_styles,
    render_card,
    render_debug_expander,
    render_empty_state,
    render_metric_card,
    render_section_title,
)
from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.workflows.nightly_memory_workflow import NightlyMemoryWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow


def render_nightly_review_panel(settings: Settings) -> None:
    inject_global_styles()
    review_date = st.date_input("回顾日期", key="nightly_date").isoformat()
    if st.button("运行晚间回顾", type="primary", key="nightly_run"):
        with st.spinner("正在运行 Nightly Memory Update..."):
            result = NightlyMemoryWorkflow(settings).run(
                review_date=review_date or local_today(),
            )
        st.session_state.latest_nightly_review = result.to_dict()

    result = st.session_state.get("latest_nightly_review")
    if result:
        render_latest_result(result)

    with st.expander("最近晚间回顾", expanded=False):
        latest = WorkspaceWorkflow().list_latest_reviews(limit=5)
        if latest:
            for review in latest:
                render_review_history_card(review)
        else:
            render_empty_state("还没有晚间回顾记录", "收集一天的对话和学习证据后，可以运行晚间回顾。")


def render_latest_result(result: dict) -> None:
    gate_results = result.get("gate_results") or []
    skipped = [
        item
        for item in gate_results
        if item.get("operation") == "skip" or item.get("validation_status") in {"failed", "skipped"}
    ]

    col_events, col_problems, col_memory, col_skipped = st.columns(4)
    with col_events:
        render_metric_card("原始证据", result.get("raw_events_count", 0))
    with col_problems:
        render_metric_card("写入问题", len(result.get("inserted_problem_ids") or []))
    with col_memory:
        render_metric_card("写入记忆", len(result.get("inserted_memory_ids") or []))
    with col_skipped:
        render_metric_card("跳过候选", len(skipped))

    parse_status = result.get("parse_status", "unknown")
    if parse_status == "failed":
        st.warning("本次结构化解析失败，详细错误已保存到开发调试信息，未写入长期表。")
        render_debug_expander(
            {
                "error_message": result.get("error_message", ""),
                "validation_errors": result.get("validation_errors") or [],
            }
        )
        return

    if parse_status == "partial_success":
        st.info("本次部分成功：可用候选已进入 graph/gate，坏候选已跳过并记录原因。")

    payload = result.get("result") or {}
    if payload.get("daily_summary"):
        render_card("当天总结", payload["daily_summary"], badge="摘要")

    render_candidate_cards("候选问题", payload.get("discovered_problems") or [], "description")
    render_candidate_cards("候选记忆", payload.get("memory_updates") or [], "content")
    render_candidate_cards("候选技能", payload.get("skill_updates") or [], "skill_name")

    if gate_results:
        operation_counts = Counter(str(item.get("operation") or "unknown") for item in gate_results)
        render_card(
            "Gate 结果",
            f"操作统计：{dict(operation_counts)}",
            footer="详细候选、校验和 embedding 诊断已收起。",
            badge="诊断",
        )

    render_diagnostics(result)


def render_candidate_cards(title: str, items: list[dict], title_key: str) -> None:
    if not items:
        return
    render_section_title(title)
    for item in items[:3]:
        card_title = str(item.get(title_key) or item.get("operation") or title)
        body = str(
            item.get("suggested_action")
            or item.get("reason")
            or item.get("root_cause")
            or item.get("description")
            or ""
        )
        render_card(card_title, body=body or None)
    if len(items) > 3:
        st.caption(f"还有 {len(items) - 3} 条候选，已放入开发调试信息。")


def render_diagnostics(result: dict) -> None:
    debug = {
        "gate_results": result.get("gate_results") or [],
        "validation_errors": result.get("validation_errors") or [],
        "normalization_diagnostics": result.get("normalization_diagnostics") or [],
        "candidate_results": result.get("candidate_results") or [],
    }
    render_debug_expander(debug)


def render_review_history_card(review: dict) -> None:
    status = review.get("parse_status") or "unknown"
    render_card(
        f"回顾日期：{review.get('review_date', '')}",
        body=f"解析状态：{status}",
        footer=f"总结：{review.get('daily_summary', '')}",
    )
