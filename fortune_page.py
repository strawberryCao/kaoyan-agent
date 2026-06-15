import streamlit as st

from kaoyan_agent.core.settings import Settings
from kaoyan_agent.ui.components.minigames import render_minigame_selector
from kaoyan_agent.workflows.planning import PlanningWorkflow
from kaoyan_agent.ui.shared import local_today


def render_fortune_page(settings: Settings) -> None:
    """上岸签页面 - 整合每日签、小任务、安抚签、解压游戏"""
    
    st.title("🎋 上岸签")
    
    workflow = PlanningWorkflow(settings)
    
    # 三个主按钮
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🎴 抽每日签", use_container_width=True):
            with st.spinner("✨ 正在为你抽签..."):
                sign = workflow.generate_daily_sign()
                st.session_state['daily_sign'] = sign
                st.session_state['sign_type'] = 'daily'
                if 'soothing_result' in st.session_state:
                    del st.session_state['soothing_result']
                st.rerun()
    with col2:
        if st.button("🎲 随机小任务", use_container_width=True):
            with st.spinner("✨ 正在生成小任务..."):
                task = workflow.generate_random_task()
                st.session_state['daily_sign'] = task
                st.session_state['sign_type'] = 'task'
                if 'soothing_result' in st.session_state:
                    del st.session_state['soothing_result']
                st.rerun()
    with col3:
        if st.button("🕯️ 安抚签", use_container_width=True):
            with st.spinner("✨ 正在生成安抚签..."):
                user_state = st.session_state.get('user_state', '')
                result = workflow.generate_soothing_message(user_state)
                st.session_state['soothing_result'] = result
                if 'daily_sign' in st.session_state:
                    del st.session_state['daily_sign']
                st.rerun()
    
    # 状态输入框
    user_state = st.text_input(
        "💬 当前状态（选填）",
        placeholder="例如：学不进去 / 好累 / 焦虑...",
        key="user_state_input",
        label_visibility="collapsed"
    )
    if user_state:
        st.session_state['user_state'] = user_state
    
    st.divider()
    
    # ========== 显示安抚签 ==========
    if 'soothing_result' in st.session_state:
        result = st.session_state['soothing_result']
        
        # 等级表情
        level_emoji = {
            "gentle": "🍃",
            "warm": "☀️",
            "energetic": "⚡",
            "calm": "🌙"
        }.get(result.get('level', 'calm'), "🌸")
        
        # 显示安抚语句卡片
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #a8edea 0%, #fed6e3 100%); border-radius: 20px; padding: 24px; text-align: center; margin: 16px 0;">
            <div style="font-size: 48px;">{level_emoji}</div>
            <div style="font-size: 18px; line-height: 1.6; margin: 12px 0;">「{result.get('message', '')}」</div>
            <div style="font-size: 14px; color: #666;">✨ {result.get('action_suggestion', '给自己一个微笑')}</div>
        </div>
        """, unsafe_allow_html=True)
        
        # 可选小任务
        small_task = result.get('small_task')
        if small_task:
            st.markdown("#### 📌 可选小任务")
            st.markdown(f"""
            <div style="background: #f0f4ff; border-radius: 12px; padding: 12px 16px; margin: 8px 0; border-left: 3px solid #667eea;">
                <b>{small_task.get('title', '')}</b><br>
                <span style="font-size: 12px; color: #666;">⏱️ {small_task.get('estimated_minutes', 0)}分钟 · {small_task.get('subject', '')}</span>
                <p style="font-size: 13px; margin-top: 4px;">💡 {small_task.get('reason', '')}</p>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("➕ 加入今日任务", key="add_soothing_task"):
                workflow.create_task(
                    title=small_task.get('title', ''),
                    subject=small_task.get('subject', ''),
                    estimated_minutes=small_task.get('estimated_minutes', 5),
                    source="soothing",
                    scheduled_date=local_today(),
                )
                st.success("✅ 已加入今日任务")
                st.rerun()
        
        # 解压小游戏
        st.markdown("#### 🎮 解压小游戏")
        render_minigame_selector()
        
        if st.button("🔄 再来一张", key="new_soothing"):
            del st.session_state['soothing_result']
            st.rerun()
    
    # ========== 显示每日签/随机任务 ==========
    if 'daily_sign' in st.session_state:
        data = st.session_state['daily_sign']
        sign_type = st.session_state.get('sign_type', 'daily')
        
        if sign_type == 'daily':
            level_map = {"top": "🏆 上上签", "good": "🌟 上吉", "steady": "📈 中吉", "small": "🌱 小吉", "calm": "🍃 平签"}
            level_display = level_map.get(data.get('sign_level', ''), '📿 吉签')
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #f5af19 0%, #f12711 100%); border-radius: 20px; padding: 24px; text-align: center; color: white; margin: 16px 0;">
                <div style="font-size: 36px;">{level_display}</div>
                <div style="font-size: 18px; margin: 12px 0;">「{data.get('sign_text', '')}」</div>
                <div style="font-size: 14px; opacity: 0.9;">💡 {data.get('today_advice', '')}</div>
            </div>
            """, unsafe_allow_html=True)
            
            if data.get('action'):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"**🎯 今日行动**\n\n{data['action']}")
                with col_b:
                    if st.button("➕ 加入任务", key="add_sign"):
                        workflow.create_task(
                            title=data['action'],
                            subject="",
                            estimated_minutes=10,
                            source="daily_sign",
                            scheduled_date=local_today(),
                        )
                        st.success("✅ 已加入")
        
        else:  # 随机任务
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #e8f4f8 0%, #d1e8f0 100%); border-radius: 16px; padding: 20px; margin: 16px 0;">
                <h3 style="margin:0 0 8px 0;">📌 {data.get('title', '')}</h3>
                <p>📖 {data.get('subject', '')} · ⏱️ {data.get('estimated_minutes', 0)} 分钟</p>
                <p>💡 {data.get('reason', '')}</p>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("➕ 加入今日任务", key="add_task"):
                workflow.create_task(
                    title=data.get('title', ''),
                    subject=data.get('subject', ''),
                    estimated_minutes=data.get('estimated_minutes', 5),
                    source="random_task",
                    scheduled_date=local_today(),
                )
                st.success("✅ 已加入今日任务")
        
        if st.button("🗑️ 关闭", key="close_result"):
            del st.session_state['daily_sign']
            st.rerun()
