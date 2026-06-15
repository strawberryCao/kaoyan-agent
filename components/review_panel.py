"""刷题复刷面板 - 修复 session_state 冲突"""

import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.shared import local_today
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow
from kaoyan_agent.agents.review_grader import ReviewGraderAgent
from kaoyan_agent.repositories.review_attempts import ReviewAttemptRepository
from kaoyan_agent.repositories.mistake_review_repository import MistakeReviewRepository


def render_review_panel(settings: Settings) -> None:
    """刷题复刷面板"""
    
    st.subheader("📝 刷题复刷")
    
    workflow = PlanningWorkflow(settings)
    workspace = WorkspaceWorkflow()
    grader = ReviewGraderAgent(settings)
    attempt_repo = ReviewAttemptRepository()
    mistake_repo = MistakeReviewRepository()
    
    # 初始化 session_state
    if 'review_hints_data' not in st.session_state:
        st.session_state.review_hints_data = None
    if 'review_question' not in st.session_state:
        st.session_state.review_question = ""
    if 'review_subject_val' not in st.session_state:
        st.session_state.review_subject_val = ""
    if 'review_topic_val' not in st.session_state:
        st.session_state.review_topic_val = ""
    if 'selected_hint' not in st.session_state:
        st.session_state.selected_hint = None
    if 'grading_result' not in st.session_state:
        st.session_state.grading_result = None
    
    # 输入区域
    with st.expander("✏️ 输入问题，生成复刷提示", expanded=True):
        question = st.text_area("💬 问题或错题描述", height=100, key="review_question_input")
        col1, col2 = st.columns(2)
        with col1:
            subject = st.text_input("📖 科目", key="review_subject_input")
        with col2:
            chapter = st.text_input("📚 章节", key="review_chapter_input")
        
        if st.button("✨ 生成复刷提示", type="primary"):
            if question.strip():
                with st.spinner("生成中..."):
                    hints = workflow.generate_review_hints(
                        question=question, subject=subject, chapter=chapter
                    )
                    st.session_state.review_hints_data = hints
                    st.session_state.review_question = question
                    st.session_state.review_subject_val = subject or hints.subject
                    st.session_state.review_topic_val = chapter or hints.topic
                    st.rerun()
    
    # 显示提示
    if st.session_state.review_hints_data:
        hints = st.session_state.review_hints_data
        
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 16px; padding: 16px; margin: 12px 0; color: white;">
            <h4>🎯 {st.session_state.review_subject_val} / {st.session_state.review_topic_val}</h4>
            <p>{hints.suggestion}</p>
        </div>
        """, unsafe_allow_html=True)
        
        for i, hint in enumerate(hints.hints, 1):
            cols = st.columns([5, 1.5])
            with cols[0]:
                st.markdown(f"**{i}. {hint.content}**")
                st.caption(f"⏱️ {hint.estimated_minutes}分钟 · {hint.hint_type}")
            with cols[1]:
                if st.button("📝 练习", key=f"practice_{i}"):
                    st.session_state.selected_hint = hint.model_dump()
                    st.session_state.selected_hint_index = i
                    st.rerun()
            st.divider()
    
    # 练习和批改
    if st.session_state.selected_hint:
        hint = st.session_state.selected_hint
        
        st.markdown("---")
        st.markdown(f"### 📝 练习")
        st.info(f"**提示：** {hint['content']}")
        
        user_answer = st.text_area("✍️ 你的理解/答案", height=150, key="user_answer_input")
        
        if st.button("🎯 提交批改", type="primary"):
            if user_answer.strip():
                with st.spinner("批改中..."):
                    result = grader.grade(
                        question=st.session_state.review_question,
                        hint=hint['content'],
                        user_answer=user_answer
                    )
                    
                    # 保存复刷记录
                    attempt_repo.create(
                        subject=st.session_state.review_subject_val,
                        topic=st.session_state.review_topic_val,
                        question=st.session_state.review_question,
                        hint_content=hint['content'],
                        user_answer=user_answer,
                        ai_feedback=result.feedback,
                        is_correct=result.is_correct,
                        confidence=result.confidence_suggestion,
                    )
                    
                    # 自动更新错题卡掌握度
                    existing_card = mistake_repo.get_card_by_question(
                        st.session_state.review_question
                    )
                    
                    if existing_card:
                        new_score = result.mastery_score or result.confidence_suggestion
                        if result.is_correct == 1:
                            new_status = "mastered" if new_score >= 80 else "reviewing"
                        elif result.is_correct == -1:
                            new_status = "reviewing"
                        else:
                            new_status = "unmastered"
                        
                        mistake_repo.update_mastery(
                            card_id=existing_card['id'],
                            mastery_status=new_status,
                            mastery_score=new_score
                        )
                        st.success(f"✅ 已更新错题卡掌握度: {new_score}%")
                    
                    st.session_state.grading_result = {
                        'is_correct': result.is_correct,
                        'feedback': result.feedback,
                        'correct_answer_hint': result.correct_answer_hint,
                        'confidence_suggestion': result.confidence_suggestion,
                        'mastery_score': result.mastery_score or result.confidence_suggestion
                    }
                    st.rerun()
        
        # 显示批改结果
        if st.session_state.grading_result:
            r = st.session_state.grading_result
            
            if r['is_correct'] == 1:
                color = "green"
                emoji = "✅"
                title = "回答正确"
            elif r['is_correct'] == -1:
                color = "orange"
                emoji = "⚠️"
                title = "部分正确"
            else:
                color = "red"
                emoji = "❌"
                title = "需要加强"
            
            st.markdown(f"""
            <div style="background: {color}10; border-left: 4px solid {color}; padding: 16px; margin: 16px 0; border-radius: 8px;">
                <h4>{emoji} {title}</h4>
                <p><strong>反馈：</strong>{r['feedback']}</p>
                <p><strong>思路提示：</strong>{r['correct_answer_hint']}</p>
                <p><strong>掌握度：</strong>{r['mastery_score']}%</p>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("继续练习", key="continue_practice"):
                st.session_state.selected_hint = None
                st.session_state.grading_result = None
                st.rerun()
    
    # 从问题板选择
    with st.expander("📋 从问题板选择"):
        problems = workspace.list_open_problems()
        if problems:
            problem_options = {f"#{p['id']} [{p.get('subject', '')}] {p.get('description', '')[:50]}": p["id"] for p in problems}
            selected = st.selectbox("选择待复刷的问题", list(problem_options.keys()), key="problem_select")
            if st.button("🎯 从问题生成复刷提示", use_container_width=True, key="from_problem_btn"):
                with st.spinner("正在生成复刷提示..."):
                    hints = workflow.generate_review_hints(from_problem_id=problem_options[selected])
                    st.session_state.review_hints_data = hints
                    problem = next(p for p in problems if p['id'] == problem_options[selected])
                    st.session_state.review_question = problem.get('description', '')
                    st.session_state.review_subject_val = problem.get('subject', '')
                    st.rerun()
        else:
            st.info("暂无打开的问题，运行晚间回顾后会有问题出现")
    
    # 查看复刷历史
    with st.expander("📊 复刷历史"):
        if st.session_state.review_subject_val:
            stats = attempt_repo.get_statistics(st.session_state.review_subject_val)
            if stats['total'] > 0:
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("总练习次数", stats['total'])
                with col2:
                    st.metric("正确率", f"{stats['correct_rate']}%")
                with col3:
                    st.metric("正确", stats['correct_count'])
                with col4:
                    st.metric("平均掌握度", f"{stats['avg_confidence']}%")
            else:
                st.info("还没有复刷记录，先练习一题吧")
        else:
            st.info("选择科目后查看复刷历史")
