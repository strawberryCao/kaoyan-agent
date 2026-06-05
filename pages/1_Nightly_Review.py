import streamlit as st

from config import get_settings
from db.database import init_db
from ui.nightly_review import render_nightly_result, run_nightly_memory_update


st.set_page_config(page_title="Nightly Review")

settings = get_settings()
init_db()

st.title("Nightly Review")
st.caption("内部复盘页：生成晚间记忆更新，并写入 nightly_reviews、problem_board 和 memories。")

with st.sidebar:
    st.caption("V0.3")
    st.write(f"Model: `{settings.llm_model}`")
    st.write(f"Database: `{settings.database_path}`")

if st.button("生成今晚记忆更新", type="primary", use_container_width=True):
    with st.spinner("正在生成今晚记忆更新..."):
        st.session_state.latest_nightly_review = run_nightly_memory_update(settings)

if "latest_nightly_review" in st.session_state:
    render_nightly_result(st.session_state.latest_nightly_review)
else:
    st.info("点击按钮后，这里会显示本次 Nightly Memory Update 的结果。")
