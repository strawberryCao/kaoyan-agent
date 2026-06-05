import streamlit as st

from config import get_settings
from db.database import get_memories, init_db


st.set_page_config(page_title="Memories")

settings = get_settings()
init_db()

st.title("Memories")
st.caption("内部长期记忆表：用于检查 Nightly Memory Update 写入的记忆。")

with st.sidebar:
    st.caption("V0.3")
    st.write(f"Model: `{settings.llm_model}`")
    st.write(f"Database: `{settings.database_path}`")

memories = get_memories()
if memories:
    st.dataframe(memories, use_container_width=True)
else:
    st.info("暂无长期记忆。")
