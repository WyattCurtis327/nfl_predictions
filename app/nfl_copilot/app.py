"""NFL Copilot — unified predictions, PBP analytics, and RCA workspace."""

from __future__ import annotations

import streamlit as st

from theme import inject_theme

st.set_page_config(
    page_title="NFL Copilot",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

pages = [
    st.Page("views/home.py", title="Home", icon="🏠", default=True),
    st.Page("views/chat.py", title="Chat", icon="💬"),
    st.Page("views/picks.py", title="Picks", icon="🎯"),
    st.Page("views/rca.py", title="Misses & RCA", icon="🔬"),
    st.Page("views/team_ratings.py", title="Team Ratings", icon="📊"),
    st.Page("views/model_stack.py", title="Model Stack", icon="🧩"),
    st.Page("views/ops.py", title="Operations", icon="⚙️"),
]

pg = st.navigation(pages)
pg.run()