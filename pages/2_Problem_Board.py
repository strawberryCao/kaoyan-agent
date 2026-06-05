import streamlit as st

from config import get_settings
from db.database import get_open_problems, init_db


st.set_page_config(page_title="Problem Board")

settings = get_settings()
init_db()

st.title("Problem Board")
st.caption("内部问题黑板：只展示当前 open 状态的问题。")

with st.sidebar:
    st.caption("V0.3")
    st.write(f"Model: `{settings.llm_model}`")
    st.write(f"Database: `{settings.database_path}`")

open_problems = get_open_problems()
if open_problems:
    st.dataframe(open_problems, use_container_width=True)
else:
    st.info("暂无 open 状态问题。")
