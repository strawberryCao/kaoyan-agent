from datetime import datetime
from typing import Any, Dict, List

import streamlit as st

from agents.checkpoint_agent import CheckpointAgent
from agents.intervention_agent import InterventionAgent
from agents.mistake_review_agent import MISTAKE_REASON_LABELS, MistakeReviewAgent
from db.database import (
    add_checkpoint_record,
    add_daily_sign,
    add_mistake_card,
    add_study_task,
    get_mistake_reason_counts,
    list_checkpoint_records,
    list_daily_signs,
    list_mistake_cards,
    list_study_tasks,
    update_mistake_mastery_status,
    update_study_task_status,
)


DEFAULT_STUDY_TASKS = [
    {
        "title": "复刷极限错题 1 道",
        "subject": "数学一",
        "estimated_minutes": 25,
        "source": "默认示例",
    },
    {
        "title": "复习操作系统进程与线程",
        "subject": "408",
        "estimated_minutes": 20,
        "source": "默认示例",
    },
    {
        "title": "背诵核心单词 30 个",
        "subject": "英语一",
        "estimated_minutes": 15,
        "source": "默认示例",
    },
]


STATUS_LABELS = {
    "todo": "待开始",
    "doing": "进行中",
    "done": "已完成",
    "skipped": "已放弃",
}


MASTERY_STATUS_LABELS = {
    "unmastered": "未掌握",
    "reviewing": "复刷中",
    "mastered": "已掌握",
}


def today_str() -> str:
    return datetime.now().astimezone().date().isoformat()


def render_today_dashboard() -> None:
    st.title("今日作战台")

    date_key = today_str()
    tasks = list_study_tasks(date_key)
    total_count = len(tasks)
    done_count = sum(1 for task in tasks if task["status"] == "done")
    total_minutes = sum(int(task.get("estimated_minutes") or 0) for task in tasks)
    completion_rate = f"{round(done_count / total_count * 100)}%" if total_count else "0%"

    metric_cols = st.columns(4)
    metric_cols[0].metric("今日任务总数", total_count)
    metric_cols[1].metric("已完成任务数", done_count)
    metric_cols[2].metric("完成率", completion_rate)
    metric_cols[3].metric("预计总学习时长", f"{total_minutes} 分钟")

    if st.button("生成一个默认今日任务示例", use_container_width=True):
        for task in DEFAULT_STUDY_TASKS:
            add_study_task(**task)
        st.success("已加入默认任务示例。")
        st.rerun()

    with st.form("add_study_task_form", clear_on_submit=True):
        st.subheader("新增任务")
        title = st.text_input("任务标题")
        col_subject, col_minutes = st.columns(2)
        subject = col_subject.text_input("科目")
        estimated_minutes = col_minutes.number_input(
            "预计耗时（分钟）",
            min_value=0,
            max_value=600,
            value=25,
            step=5,
        )
        source = st.text_input("来源", value="手动新增")
        submitted = st.form_submit_button("保存任务", use_container_width=True)

    if submitted:
        if not title.strip():
            st.error("任务标题不能为空。")
        else:
            add_study_task(
                title=title,
                subject=subject,
                estimated_minutes=int(estimated_minutes),
                source=source,
            )
            st.success("任务已保存。")
            st.rerun()

    st.subheader("今日任务")
    tasks = list_study_tasks(date_key)
    if not tasks:
        st.info("今天还没有任务。")
        return

    for task in tasks:
        render_task_row(task)


def render_task_row(task: Dict[str, Any]) -> None:
    with st.container(border=True):
        title_col, status_col = st.columns([3, 1])
        title_col.markdown(f"**{task['title']}**")
        status_col.markdown(f"**{STATUS_LABELS.get(task['status'], task['status'])}**")
        st.caption(
            f"科目：{task.get('subject') or '-'} | "
            f"预计耗时：{task.get('estimated_minutes') or 0} 分钟 | "
            f"来源：{task.get('source') or '-'}"
        )

        col_start, col_done, col_skip = st.columns(3)
        if col_start.button("开始", key=f"task_start_{task['id']}", use_container_width=True):
            update_study_task_status(task["id"], "doing")
            st.rerun()
        if col_done.button("完成", key=f"task_done_{task['id']}", use_container_width=True):
            update_study_task_status(task["id"], "done")
            st.rerun()
        if col_skip.button("放弃", key=f"task_skip_{task['id']}", use_container_width=True):
            update_study_task_status(task["id"], "skipped")
            st.rerun()


def render_mistake_review_pool(settings) -> None:
    st.title("错题复刷池")

    reason_counts = get_mistake_reason_counts()
    if reason_counts:
        readable_counts = [
            {
                "错因标签": MISTAKE_REASON_LABELS.get(
                    row["mistake_reason"], row["mistake_reason"]
                ),
                "数量": row["count"],
            }
            for row in reason_counts
        ]
        st.subheader("错因统计")
        st.table(readable_counts)

    with st.form("mistake_card_form", clear_on_submit=True):
        st.subheader("录入错题")
        col_subject, col_chapter = st.columns(2)
        subject = col_subject.text_input("科目", value="数学一")
        chapter = col_chapter.text_input("章节", value="极限")
        question = st.text_area("错题内容", height=140)
        user_reason = st.text_area("自己认为错在哪里（可选）", height=90)
        submitted = st.form_submit_button("生成错题卡片", use_container_width=True)

    if submitted:
        if not question.strip():
            st.error("错题内容不能为空。")
        else:
            with st.spinner("正在生成错题卡片..."):
                card = MistakeReviewAgent(settings).generate_card(
                    subject=subject,
                    chapter=chapter,
                    question=question,
                    user_reason=user_reason,
                )
            add_mistake_card(
                subject=subject,
                chapter=chapter,
                question=question,
                analysis=card["analysis"],
                mistake_reason=card["mistake_reason"],
                knowledge_points=card["knowledge_points"],
                review_priority=card["review_priority"],
            )
            st.session_state.latest_mistake_card = card
            st.success("错题卡片已生成并保存。")
            st.rerun()

    cards = list_mistake_cards()
    st.subheader("错题卡片")
    if not cards:
        st.info("还没有错题卡片。")
        return

    for card in cards:
        render_mistake_card(card)


def render_mistake_card(card: Dict[str, Any]) -> None:
    with st.container(border=True):
        header_col, status_col = st.columns([3, 1])
        header_col.markdown(
            f"**{card.get('subject') or '未填写科目'} / {card.get('chapter') or '未填写章节'}**"
        )
        status_col.markdown(
            f"**{MASTERY_STATUS_LABELS.get(card['mastery_status'], card['mastery_status'])}**"
        )
        st.caption(
            f"错因：{MISTAKE_REASON_LABELS.get(card['mistake_reason'], card['mistake_reason'])} | "
            f"复刷优先级：{card['review_priority']}"
        )
        st.write("知识点：", card["knowledge_points"] or "-")
        st.write("分析：", card["analysis"] or "-")
        with st.expander("查看错题内容"):
            st.write(card["question"])

        statuses = list(MASTERY_STATUS_LABELS.keys())
        current_index = statuses.index(card["mastery_status"]) if card["mastery_status"] in statuses else 0
        selected = st.selectbox(
            "掌握状态",
            statuses,
            index=current_index,
            format_func=lambda value: MASTERY_STATUS_LABELS[value],
            key=f"mastery_select_{card['id']}",
        )
        if st.button(
            "更新掌握状态",
            key=f"mastery_update_{card['id']}",
            use_container_width=True,
        ):
            update_mistake_mastery_status(card["id"], selected)
            st.success("掌握状态已更新。")
            st.rerun()


def render_checkpoint_page(settings) -> None:
    st.title("章节闯关验收")

    col_subject, col_chapter = st.columns(2)
    subject = col_subject.text_input("科目", value="数学一", key="checkpoint_subject")
    chapter = col_chapter.text_input("章节", value="极限", key="checkpoint_chapter")

    if st.button("生成验收题", type="primary", use_container_width=True):
        if not subject.strip() or not chapter.strip():
            st.error("科目和章节不能为空。")
        else:
            with st.spinner("正在生成验收题..."):
                questions = CheckpointAgent(settings).generate_questions(subject, chapter)
            st.session_state.checkpoint_context = {
                "subject": subject,
                "chapter": chapter,
                "questions": questions,
            }
            st.success("验收题已生成。")

    context = st.session_state.get("checkpoint_context")
    if context:
        st.subheader("本次验收题")
        for index, question in enumerate(context["questions"], start=1):
            st.write(f"{index}. {question}")

        user_answer = st.text_area("填写回答", height=180, key="checkpoint_answer")
        if st.button("提交验收", use_container_width=True):
            with st.spinner("正在评分..."):
                result = CheckpointAgent(settings).grade_answer(
                    subject=context["subject"],
                    chapter=context["chapter"],
                    questions=context["questions"],
                    user_answer=user_answer,
                )
            record_id = add_checkpoint_record(
                subject=context["subject"],
                chapter=context["chapter"],
                user_answer=user_answer,
                score=result["score"],
                passed=result["passed"],
                feedback=result["feedback"],
                weak_points=result["weak_points"],
            )
            st.session_state.latest_checkpoint_result = {
                **result,
                "record_id": record_id,
                "subject": context["subject"],
                "chapter": context["chapter"],
            }
            st.success("验收记录已保存。")

    latest_result = st.session_state.get("latest_checkpoint_result")
    if latest_result:
        st.subheader("最近一次验收结果")
        result_cols = st.columns(3)
        result_cols[0].metric("分数", latest_result["score"])
        result_cols[1].metric("是否通过", "通过" if latest_result["passed"] else "未通过")
        result_cols[2].metric("记录 ID", latest_result["record_id"])
        st.write("薄弱点：", latest_result["weak_points"])
        st.write("反馈：", latest_result["feedback"])

        if not latest_result["passed"]:
            if st.button("生成复习任务并加入今日作战台", use_container_width=True):
                add_study_task(
                    title=f"复习 {latest_result['chapter']} 薄弱点",
                    subject=latest_result["subject"],
                    estimated_minutes=20,
                    source="章节闯关未通过",
                )
                st.success("复习任务已加入今日作战台。")

    records = list_checkpoint_records(limit=30)
    st.subheader("历史验收记录")
    if records:
        table_rows = [
            {
                "ID": record["id"],
                "科目": record["subject"],
                "章节": record["chapter"],
                "分数": record["score"],
                "是否通过": "通过" if record["passed"] else "未通过",
                "薄弱点": record["weak_points"],
                "创建时间": record["created_at"],
            }
            for record in records
        ]
        st.dataframe(table_rows, use_container_width=True)
    else:
        st.info("还没有章节验收记录。")


def render_sign_and_random_task_page(settings) -> None:
    st.title("上岸签 / 随机任务")
    agent = InterventionAgent(settings)

    tab_sign, tab_random, tab_soothing = st.tabs(["每日上岸签", "随机任务", "安抚签"])

    with tab_sign:
        if st.button("抽取今日上岸签", type="primary", use_container_width=True):
            sign = agent.generate_daily_sign()
            sign_id = add_daily_sign(
                sign_level=sign["sign_level"],
                sign_text=sign["sign_text"],
                today_advice=sign["today_advice"],
            )
            st.session_state.latest_daily_sign = {**sign, "id": sign_id}
            st.success("今日上岸签已保存。")

        sign = st.session_state.get("latest_daily_sign")
        if sign:
            render_daily_sign(sign)

        signs = list_daily_signs(limit=10)
        if signs:
            st.subheader("最近上岸签")
            st.dataframe(signs, use_container_width=True)

    with tab_random:
        if st.button("生成随机任务", type="primary", use_container_width=True):
            st.session_state.latest_random_task = agent.generate_random_task()

        task = st.session_state.get("latest_random_task")
        if task:
            render_task_candidate(task, source="随机任务", button_key="add_random_task")

    with tab_soothing:
        user_state = st.text_input("当前状态", placeholder="例如：学不进去、好累、很焦虑")
        if st.button("生成低能量任务", type="primary", use_container_width=True):
            st.session_state.latest_soothing_task = agent.generate_soothing_task(user_state)

        task = st.session_state.get("latest_soothing_task")
        if task:
            render_task_candidate(task, source="安抚签", button_key="add_soothing_task")


def render_daily_sign(sign: Dict[str, Any]) -> None:
    with st.container(border=True):
        st.markdown(f"**{sign['sign_level']}**")
        st.write(sign["sign_text"])
        st.write("今日建议：", sign["today_advice"])
        if sign.get("action"):
            st.write("可选行动：", sign["action"])


def render_task_candidate(task: Dict[str, Any], source: str, button_key: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{task['title']}**")
        st.caption(
            f"科目：{task.get('subject') or '综合'} | "
            f"预计耗时：{task.get('estimated_minutes') or 5} 分钟"
        )
        st.write("理由：", task.get("reason") or "-")
        if st.button("加入今日作战台", key=button_key, use_container_width=True):
            add_study_task(
                title=task["title"],
                subject=task.get("subject") or "综合",
                estimated_minutes=int(task.get("estimated_minutes") or 5),
                source=source,
            )
            st.success("任务已加入今日作战台。")
