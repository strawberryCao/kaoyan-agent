import streamlit as st
import pandas as pd

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.workflows.workspace_workflow import WorkspaceWorkflow
from kaoyan_agent.agents.score_predictor import ScorePredictorAgent


def render_score_trend_panel(settings: Settings) -> None:
    """成绩趋势面板 - 带AI建议和预测"""
    
    st.subheader("📊 成绩记录与趋势分析")
    
    workspace = WorkspaceWorkflow()
    workflow = PlanningWorkflow(settings)
    
    # 录入成绩表单
    with st.expander("✏️ 录入新成绩", expanded=True):
        with st.form("score_record_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                subject = st.text_input("科目", placeholder="数学/英语/408...")
            with col2:
                score = st.number_input("分数", min_value=0.0, max_value=150.0, value=0.0)
            with col3:
                full_score = st.number_input("满分", min_value=1.0, value=100.0)
            
            exam_type = st.selectbox("考试类型", ["模拟考", "真题", "章节测试", "月考", "其他"])
            exam_date = st.date_input("考试日期")
            note = st.text_area("备注", placeholder="可以记录考试感受、薄弱环节...", height=60)
            
            submitted = st.form_submit_button("💾 保存成绩", type="primary", use_container_width=True)
            
            if submitted and subject.strip():
                workflow.record_score(
                    subject=subject,
                    score=float(score),
                    full_score=float(full_score),
                    exam_type=exam_type,
                    exam_date=exam_date.isoformat(),
                    note=note,
                )
                st.success(f"✅ 已保存 {subject} 成绩 {score}/{full_score}")
                st.rerun()
    
    st.divider()
    
    # 获取所有有成绩的科目
    all_records = workspace.list_score_records(limit=500)
    subjects = list(set([r.get('subject', '') for r in all_records if r.get('subject')]))
    
    if not subjects:
        st.info("📭 还没有成绩记录，先录入一些模考成绩吧")
        return
    
    selected_subject = st.selectbox("📚 选择科目查看趋势", subjects, key="score_subject")
    
    # 获取该科目的成绩记录
    subject_records = workspace.list_score_records(subject=selected_subject, limit=50)
    
    if subject_records:
        # 转换为百分制用于图表
        df_data = []
        for r in subject_records:
            percent = round(r.get('score', 0) / max(r.get('full_score', 100), 1) * 100, 1)
            df_data.append({
                "日期": r.get('exam_date', '')[:10],
                "成绩(%)": percent,
                "原始分": f"{r.get('score', 0)}/{r.get('full_score', 100)}"
            })
        df = pd.DataFrame(df_data)
        
        # 显示表格
        st.markdown("#### 📋 成绩记录")
        st.dataframe(df, use_container_width=True)
        
        # 显示趋势图
        st.markdown("#### 📈 成绩趋势图")
        st.line_chart(df.set_index("日期")["成绩(%)"])
        
        # AI 分析建议
        st.markdown("#### 🤖 AI 分析建议")
        
        with st.spinner("正在分析成绩趋势..."):
            analysis = workflow.analyze_score_trend(selected_subject)
        
        if analysis:
            risk_colors = {"low": "🟢", "medium": "🟡", "high": "🔴"}
            risk_text = {"low": "趋势良好", "medium": "需要关注", "high": "急需改进"}
            trend_text = {
                "improving": "📈 上升趋势",
                "declining": "📉 下降趋势",
                "stable": "➡️ 平稳趋势",
                "fluctuating": "📊 波动较大"
            }
            
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-radius: 16px; padding: 20px; margin: 12px 0;">
                <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 12px;">
                    <span style="font-size: 24px;">{risk_colors.get(analysis.get('risk_level', 'medium'), '🟡')}</span>
                    <span style="font-weight: bold;">{trend_text.get(analysis.get('trend', 'stable'), '')}</span>
                    <span style="color: #666;">{risk_text.get(analysis.get('risk_level', 'medium'), '')}</span>
                </div>
                <div style="font-size: 16px; line-height: 1.5; color: #333;">
                    💡 {analysis.get('suggestion', '')}
                </div>
                <div style="margin-top: 12px;">
                    <span style="font-size: 14px; color: #666;">🎯 关注点：</span>
                    {', '.join([f'<span style="background: #e9ecef; padding: 2px 8px; border-radius: 12px; margin: 0 4px; font-size: 12px;">{p}</span>' for p in analysis.get('focus_points', [])])}
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("📊 至少需要2次成绩记录才能生成趋势分析")
        
        # 成绩预测（需要至少3次记录）
        if len(subject_records) >= 3:
            st.markdown("#### 🔮 成绩预测")
            
            predictor = ScorePredictorAgent(settings)
            prediction = predictor.predict(selected_subject, subject_records)
            
            if prediction:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("预测下次成绩", f"{prediction.next_score}分")
                with col2:
                    st.metric("预测区间", f"{prediction.lower_bound}-{prediction.upper_bound}分")
                with col3:
                    st.metric("置信度", f"{prediction.confidence}%")
                
                st.info(f"💡 {prediction.suggestion}")
        
        # 最近3次成绩对比
        if len(subject_records) >= 2:
            st.markdown("#### 📊 最近成绩对比")
            recent_3 = subject_records[:3]
            cols = st.columns(len(recent_3))
            for i, r in enumerate(recent_3):
                percent = round(r.get('score', 0) / max(r.get('full_score', 100), 1) * 100, 1)
                with cols[i]:
                    st.metric(
                        label=r.get('exam_date', '')[:10],
                        value=f"{percent}%",
                        delta=f"{r.get('score', 0)}/{r.get('full_score', 100)}"
                    )
    else:
        st.info(f"📭 还没有 {selected_subject} 的成绩记录")
