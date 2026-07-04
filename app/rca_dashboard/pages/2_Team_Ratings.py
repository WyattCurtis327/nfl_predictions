"""Team net offensive vs defensive rating scatter plot."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from shared import DEFAULT_SEASON, pbp_table, sql_query
from team_ratings_queries import add_net_ratings, pbp_season_weeks_sql, team_scoring_sql

st.set_page_config(page_title="Team Ratings", layout="wide", page_icon="📊")

PBP_TABLE = pbp_table()

st.title("Team Net Ratings")
st.caption(
    "Points-based team strength from play-by-play results. "
    "**Net offensive** = points scored above league average. "
    "**Net defensive** = points allowed below league average (higher is better)."
)

with st.expander("How to read this chart", expanded=False):
    st.markdown(
        """
- Each dot is one NFL team for the **season and weeks** you selected in the sidebar.
- **Right on the X-axis** = scores more than league average (good offense).
- **Higher on the Y-axis** = allows fewer points than league average (good defense).
- Teams in the **upper-right** are strong on both sides; **lower-left** are struggling.
- Change the week window to zoom in on recent form or view the full season to date.
        """
    )


@st.cache_data(ttl=300)
def load_season_weeks() -> pd.DataFrame:
    return sql_query(pbp_season_weeks_sql(PBP_TABLE))


@st.cache_data(ttl=120)
def load_team_ratings(*, season: int, weeks: tuple[int, ...]) -> pd.DataFrame:
    raw = sql_query(team_scoring_sql(PBP_TABLE, season=season, weeks=list(weeks)))
    return add_net_ratings(raw)


try:
    season_weeks = load_season_weeks()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load PBP metadata: {exc}")
    st.stop()

if season_weeks.empty:
    st.warning(f"No play-by-play games found in `{PBP_TABLE}`.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    seasons = sorted(season_weeks["season"].dropna().unique(), reverse=True)
    season = st.selectbox(
        "Season",
        options=seasons,
        index=seasons.index(DEFAULT_SEASON) if DEFAULT_SEASON in seasons else 0,
    )
    weeks_available = sorted(
        season_weeks[season_weeks["season"] == season]["week"].dropna().unique().astype(int).tolist()
    )
    weeks = st.multiselect(
        "Weeks",
        options=weeks_available,
        default=weeks_available,
        help="Select one or more weeks to include in the rating window.",
    )
    st.divider()
    st.markdown("**Source**")
    st.code(PBP_TABLE, language="sql")

if not weeks:
    st.info("Select at least one week to plot team ratings.")
    st.stop()

ratings = load_team_ratings(season=int(season), weeks=tuple(weeks))
if ratings.empty:
    st.warning("No team games matched the selected filters.")
    st.stop()

week_label = ", ".join(str(week) for week in sorted(weeks))
league_pf = ratings["league_points_for"].iloc[0]
league_pa = ratings["league_points_against"].iloc[0]

col1, col2, col3 = st.columns(3)
col1.metric("Teams", len(ratings))
col2.metric("League avg points for", f"{league_pf:.1f}")
col3.metric("League avg points against", f"{league_pa:.1f}")

fig = px.scatter(
    ratings,
    x="net_offensive",
    y="net_defensive",
    text="team",
    hover_data={
        "team": True,
        "games": True,
        "points_for_mean": ":.1f",
        "points_against_mean": ":.1f",
        "net_offensive": ":+.1f",
        "net_defensive": ":+.1f",
    },
    labels={
        "net_offensive": "Net offensive rating (PF vs league avg)",
        "net_defensive": "Net defensive rating (league avg − PA)",
        "team": "Team",
    },
    title=f"Team net ratings — {season}, weeks {week_label}",
)
fig.update_traces(textposition="top center", marker={"size": 12, "opacity": 0.85})
fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="gray")
fig.add_vline(x=0, line_width=1, line_dash="dash", line_color="gray")
fig.update_layout(
    height=620,
    xaxis=dict(zeroline=False),
    yaxis=dict(zeroline=False),
)

st.plotly_chart(fig, use_container_width=True)

st.markdown(
    "**How to read the chart:** Top-right teams score more and allow fewer points than average "
    "in the selected window. Bottom-left teams are below average on both sides."
)

display = ratings[
    [
        "team",
        "games",
        "points_for_mean",
        "points_against_mean",
        "net_offensive",
        "net_defensive",
    ]
].sort_values(["net_offensive", "net_defensive"], ascending=False)
st.subheader("Rating table")
st.dataframe(display, use_container_width=True, hide_index=True)