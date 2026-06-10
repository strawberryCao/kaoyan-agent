import streamlit as st

from db.database import init_db
from ui.focus_stats_page import render_focus_stats_page

st.set_page_config(page_title="专注统计", page_icon="📊")
init_db()
render_focus_stats_page()
