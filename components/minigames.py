"""解压小游戏集合"""

import streamlit as st
import random
import time


def render_breathing_game():
    """呼吸练习小游戏"""
    st.markdown("### 🌬️ 4-7-8 呼吸法")
    st.caption("跟着节奏呼吸，放松身心")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("😤 吸气", key="breathe_in"):
            with st.spinner("吸气 4 秒..."):
                time.sleep(0.5)
                st.toast("🌬️ 吸... 1", icon="💨")
                time.sleep(0.5)
                st.toast("🌬️ 吸... 2", icon="💨")
                time.sleep(0.5)
                st.toast("🌬️ 吸... 3", icon="💨")
                time.sleep(0.5)
                st.toast("🌬️ 吸... 4 ✅", icon="💨")
    with col2:
        if st.button("😤 屏息", key="breathe_hold"):
            with st.spinner("屏息 7 秒..."):
                for i in range(7):
                    time.sleep(0.5)
                    st.toast(f"⏸️ {i+1}", icon="🫁")
                st.toast("✅ 屏息完成", icon="✅")
    with col3:
        if st.button("😮‍💨 呼气", key="breathe_out"):
            with st.spinner("呼气 8 秒..."):
                for i in range(8):
                    time.sleep(0.5)
                    st.toast(f"💨 呼... {i+1}", icon="🌬️")
                st.toast("✅ 呼气完成", icon="✅")
    
    st.caption("💡 完成一次完整循环 = 吸气4秒 → 屏息7秒 → 呼气8秒")


def render_mood_dice():
    """心情骰子"""
    st.markdown("### 🎲 抛个心情骰子")
    
    moods = [
        ("😊", "今天状态不错，继续保持！"),
        ("😌", "放松一点，你已经做得很好了"),
        ("🤗", "抱抱自己，你值得被温柔对待"),
        ("💪", "你比你想象中更强大"),
        ("🌟", "今天也要闪闪发光"),
        ("🍃", "像风一样自由，不必太紧张"),
        ("☕", "休息一下，喝杯水再继续"),
        ("🌸", "困难是暂时的，春天总会来"),
    ]
    
    if st.button("🎲 抛骰子", key="mood_dice"):
        mood, msg = random.choice(moods)
        st.balloons()
        st.markdown(f"""
        <div style="text-align: center; padding: 30px; background: linear-gradient(135deg, #f5f0ff 0%, #e8e0ff 100%); border-radius: 20px;">
            <div style="font-size: 80px;">{mood}</div>
            <div style="font-size: 18px; margin-top: 16px;">{msg}</div>
        </div>
        """, unsafe_allow_html=True)


def render_click_relax():
    """点击放松 - 简单解压"""
    st.markdown("### 🫧 泡泡解压")
    st.caption("点击泡泡释放压力")
    
    if 'bubble_count' not in st.session_state:
        st.session_state.bubble_count = 0
    
    cols = st.columns(5)
    for i, col in enumerate(cols):
        with col:
            if st.button(f"🫧", key=f"bubble_{i}"):
                st.session_state.bubble_count += 1
                st.toast("💥 pop!", icon="✨")
    
    if st.session_state.bubble_count > 0:
        st.caption(f"✨ 你已经戳破 {st.session_state.bubble_count} 个泡泡啦")
        if st.button("🔄 重置泡泡"):
            st.session_state.bubble_count = 0
            st.rerun()


def render_affirmation():
    """每日肯定语"""
    st.markdown("### 💫 今日肯定语")
    
    affirmations = [
        "我允许自己休息，休息是为了更好地前进",
        "每一个小小的进步都值得庆祝",
        "今天的我已经很棒了",
        "学习的过程比结果更重要",
        "我有能力解决遇到的问题",
        "我不必完美，尽力就好",
        "压力是暂时的，我的努力是持续的",
        "我正在成为更好的自己",
    ]
    
    if st.button("✨ 获得肯定语", key="affirmation"):
        affirmation = random.choice(affirmations)
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 20px; padding: 30px; text-align: center; color: white;">
            <div style="font-size: 24px; margin-bottom: 16px;">🌙</div>
            <div style="font-size: 18px; line-height: 1.6;">「{affirmation}」</div>
        </div>
        """, unsafe_allow_html=True)


def render_minigame_selector():
    """小游戏选择器"""
    
    st.markdown("### 🎮 解压小游戏")
    
    game_type = st.radio(
        "选择你想玩的小游戏",
        ["🌬️ 呼吸练习", "🎲 心情骰子", "🫧 戳泡泡", "💫 肯定语"],
        horizontal=True,
        key="minigame_selector"
    )
    
    st.divider()
    
    if game_type == "🌬️ 呼吸练习":
        render_breathing_game()
    elif game_type == "🎲 心情骰子":
        render_mood_dice()
    elif game_type == "🫧 戳泡泡":
        render_click_relax()
    elif game_type == "💫 肯定语":
        render_affirmation()
