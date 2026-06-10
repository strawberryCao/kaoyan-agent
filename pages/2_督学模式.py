import streamlit as st

from db.database import init_db
from ui.focus_timer_page import render_focus_timer_page

st.set_page_config(page_title="督学模式", page_icon="🍅")
init_db()
render_focus_timer_page()
