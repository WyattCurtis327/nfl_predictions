"""Team net ratings from play-by-play — redesigned chart."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from shared import DEFAULT_SEASON, pbp_table, sql_query
from team_ratings_queries import add_net_ratings, pbp_season_weeks_sql, team_scoring_sql
from theme import section_header

PBP_TABLE = pbp_table()

PLOTLY_TEMPLATE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="#121a24",
    font=dict(family="DM Sans, sans-serif", color="#e8edf4"),
    xaxis=dict(gridcolor="#2a3648", zerolinecolor="#2a3648"),
    yaxis=dict(gridcolor="#2a3648", zerolinecolor="#2a3648"),
)


@st.cache_data(ttl=300)
def load_season_weeks() -> pd.DataFrame:
    return sql_query(pbp_season_weeks_sql(PBP_TABLE))


@st.cache_data(ttl=120)
def load_team_ratings(*, season: int, weeks: tuple[int, ...]) -> pd.DataFrame:
    raw = sql_query(team_scoring_sql(PBP_TABLE, season=season, weeks=list(weeks)))
    return add_net_ratings(raw)


section_header(
    "Team Ratings",
    "Net offensive vs defensive strength from play-by-play final scores.",
)

try:
    season_weeks = load_season_weeks()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load PBP metadata: {exc}")
    st.stop()

if season_weeks.empty:
    st.warning(f"No play-by-play games found in `{PBP_TABLE}`.")
    st.stop()

with st.sidebar:
    st.markdown("##### Filters")
    seasons = sorted(season_weeks["season"].dropna().unique(), reverse=True)
    season = st.selectbox(
        "Season",
        options=seasons,
        index=seasons.index(DEFAULT_SEASON) if DEFAULT_SEASON in seasons else 0,
        key="ratings_season",
    )
    weeks_available = sorted(
        season_weeks[season_weeks["season"] == season]["week"].dropna().unique().astype(int).tolist()
    )
    weeks = st.multiselect(
        "Weeks",
        options=weeks_available,
        default=weeks_available,
        key="ratings_weeks",
    )

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

c1, c2, c3 = st.columns(3)
c1.metric("Teams", len(ratings))
c2.metric("League avg PF", f"{league_pf:.1f}")
c3.metric("League avg PA", f"{league_pa:.1f}")

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
        "net_offensive": "Net offensive (PF vs league)",
        "net_defensive": "Net defensive (league − PA)",
    },
    title=f"{season} · weeks {week_label}",
    color="net_offensive",
    color_continuous_scale=["#f07178", "#8b9bb4", "#2dd4a8"],
)
fig.update_traces(
    textposition="top center",
    marker={"size": 14, "opacity": 0.9, "line": {"width": 1, "color": "#2a3648"}},
)
fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="#5b6b82")
fig.add_vline(x=0, line_width=1, line_dash="dash", line_color="#5b6b82")
fig.update_layout(height=640, **PLOTLY_TEMPLATE)
fig.update_coloraxes(showscale=False)

st.plotly_chart(fig, use_container_width=True)
st.caption("Upper-right = strong offense and defense in the selected window.")

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
st.dataframe(display, use_container_width=True, hide_index=True)