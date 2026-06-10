import streamlit as st

from db.database import init_db
from ui.battle_station_page import render_battle_station_page

st.set_page_config(page_title="今日作战台", page_icon="📋")
init_db()
render_battle_station_page()
