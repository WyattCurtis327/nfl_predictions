"""NFL Copilot home — overview and quick navigation."""

from __future__ import annotations

import streamlit as st

from queries import list_season_weeks_sql
from shared import DEFAULT_SEASON, pick_miss_rca_view, predictions_table, sql_query
from theme import render_brand, section_header

PREDICTIONS_TABLE = predictions_table()
RCA_VIEW = pick_miss_rca_view()


@st.cache_data(ttl=120)
def load_prediction_weeks() -> int:
    frame = sql_query(list_season_weeks_sql(PREDICTIONS_TABLE))
    if frame.empty:
        return 0
    latest = frame.iloc[0]
    return int(latest["games"])


@st.cache_data(ttl=120)
def load_rca_miss_count() -> int:
    try:
        frame = sql_query(
            f"SELECT COUNT(*) AS misses FROM {RCA_VIEW} WHERE season = {DEFAULT_SEASON}"
        )
        if frame.empty:
            return 0
        return int(frame["misses"].iloc[0])
    except Exception:  # noqa: BLE001
        return 0


render_brand()

try:
    game_count = load_prediction_weeks()
    miss_count = load_rca_miss_count()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not reach Databricks SQL: {exc}")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Default season", DEFAULT_SEASON)
c2.metric("Latest week games", game_count)
c3.metric("Season misses (RCA)", miss_count)
c4.metric("Production model", "Monte Carlo")

section_header("Workspace", "Pick a view from the sidebar — everything shares the same Unity Catalog data.")

t1, t2, t3 = st.columns(3)
with t1:
    st.markdown(
        """
        <div class="home-tile">
          <h3>🎯 Weekly Picks</h3>
          <p>Card-based pick board with spread/total confidence, market lines, and projected scores.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with t2:
    st.markdown(
        """
        <div class="home-tile">
          <h3>🔬 Misses & RCA</h3>
          <p>Post-game root-cause analysis with projection pipeline charts and ranked explanations.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with t3:
    st.markdown(
        """
        <div class="home-tile">
          <h3>📊 Team Ratings</h3>
          <p>Net offensive vs defensive strength from play-by-play scoring over any week window.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

t4, t5, t6 = st.columns(3)
with t4:
    st.markdown(
        """
        <div class="home-tile">
          <h3>🧩 Model Stack</h3>
          <p>Shadow-model guide, ensemble weights, and live accuracy leaderboard when grades exist.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with t5:
    st.markdown(
        """
        <div class="home-tile">
          <h3>⚙️ Operations</h3>
          <p>Commands to rerun predictions, refresh odds, and grade completed weeks.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with t6:
    st.markdown(
        """
        <div class="home-tile">
          <h3>💬 Chat</h3>
          <p>Agent tools for picks/RCA/PBP plus Genie for accuracy questions. Open <strong>Chat</strong> in the sidebar.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

with st.expander("Data sources"):
    st.code(
        f"""
{PREDICTIONS_TABLE}
{RCA_VIEW}
nfl.landing.play_by_play
        """.strip(),
        language="sql",
    )