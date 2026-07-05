"""Missed picks with deterministic root-cause analysis."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from display_time import format_timestamp_la, format_timestamps_in_frame
from rca_queries import cause_summary_sql, list_rca_season_weeks_sql, missed_picks_sql, parse_causes
from shared import DEFAULT_SEASON, pick_miss_rca_view, sql_query

st.set_page_config(page_title="Misses & RCA", layout="wide", page_icon="🔍")

VIEW = pick_miss_rca_view()

st.title("Misses & RCA")
st.caption(
    f"Graded wrong picks with root-cause decomposition from `{VIEW}`. "
    "Times shown in America/Los_Angeles as `yyyy-MM-dd_hh_mm`."
)


@st.cache_data(ttl=120)
def load_rca_season_weeks() -> pd.DataFrame:
    return sql_query(list_rca_season_weeks_sql(VIEW))


@st.cache_data(ttl=60)
def load_misses(*, season: int, week: int) -> pd.DataFrame:
    return sql_query(missed_picks_sql(VIEW, season=season, week=week))


@st.cache_data(ttl=120)
def load_cause_summary(*, season: int) -> pd.DataFrame:
    return sql_query(cause_summary_sql(VIEW, season=season))


try:
    season_weeks = load_rca_season_weeks()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load RCA metadata: {exc}")
    st.info("Run grading with `log_rca=true`, backfill RCA, and deploy the pick_miss_rca view.")
    st.stop()

if season_weeks.empty:
    st.warning("No RCA rows yet. Grade a week with misses or run `scripts/backfill_prediction_rca.py`.")
    st.stop()

with st.sidebar:
    st.header("Filters")
    seasons = sorted(season_weeks["season"].dropna().unique(), reverse=True)
    season = st.selectbox(
        "Season",
        options=seasons,
        index=seasons.index(DEFAULT_SEASON) if DEFAULT_SEASON in seasons else 0,
    )
    weeks_for_season = season_weeks[season_weeks["season"] == season]["week"].tolist()
    week = st.selectbox("Week", options=weeks_for_season, index=0)
    st.divider()
    st.markdown("**Source**")
    st.code(VIEW, language="sql")

misses = load_misses(season=int(season), week=int(week))
causes = load_cause_summary(season=int(season))

col1, col2, col3 = st.columns(3)
col1.metric("Misses this week", len(misses))
col2.metric(
    "Spread misses",
    int((misses["miss_types"].astype(str).str.contains("spread")).sum()) if not misses.empty else 0,
)
col3.metric(
    "Total misses",
    int((misses["miss_types"].astype(str).str.contains("total")).sum()) if not misses.empty else 0,
)

if not causes.empty:
    st.subheader(f"Top causes — season {season}")
    st.bar_chart(causes.set_index("primary_cause")["misses"])

if misses.empty:
    st.success(f"No RCA rows for season {season}, week {week}.")
    st.stop()

summary_cols = [
    "gameday",
    "analyzed_at",
    "away_abbr",
    "home_abbr",
    "miss_types",
    "primary_cause",
    "spread_pick",
    "total_pick",
    "proj_away_score",
    "proj_home_score",
    "actual_away_score",
    "actual_home_score",
]
st.subheader("Miss board")
st.dataframe(
    format_timestamps_in_frame(misses[summary_cols]),
    use_container_width=True,
    hide_index=True,
)

st.subheader("Root-cause detail")
for _, row in misses.iterrows():
    title = f"{row['away_abbr']} @ {row['home_abbr']} — {row['primary_cause']}"
    with st.expander(title):
        left, right = st.columns(2)
        with left:
            st.markdown("**Projection stages**")
            st.write(
                f"PBP: {row.get('pbp_proj_away', '—')} – {row.get('pbp_proj_home', '—')} "
                f"({row.get('projection_source', '—')})"
            )
            st.write(
                f"nfelo: {row.get('nfelo_proj_away', '—')} – {row.get('nfelo_proj_home', '—')}"
            )
            st.write(
                f"Market: {row.get('market_proj_away', '—')} – {row.get('market_proj_home', '—')}"
            )
            st.write(
                f"Sim pick: {row.get('proj_away_score', '—')} – {row.get('proj_home_score', '—')}"
            )
            st.write(
                f"Actual: {row.get('actual_away_score', '—')} – {row.get('actual_home_score', '—')}"
            )
        with right:
            st.markdown("**RCA metadata**")
            st.write(f"Analyzed at: {format_timestamp_la(row.get('analyzed_at'))}")
            st.markdown("**Training profiles**")
            st.write(
                f"Home PF mean: {row.get('home_profile_pf_mean', '—')} "
                f"({row.get('profile_source', '—')})"
            )
            st.write(f"Away PF mean: {row.get('away_profile_pf_mean', '—')}")
            st.write(
                f"Turnovers: home {row.get('game_home_turnovers', '—')}, "
                f"away {row.get('game_away_turnovers', '—')}"
            )

        causes_list = parse_causes(row.get("cause_summary"))
        if causes_list:
            st.markdown("**Ranked causes**")
            for cause in causes_list:
                st.write(f"- **{cause.get('label')}**: {cause.get('detail')}")
        else:
            st.json(json.loads(row["cause_summary"]) if isinstance(row.get("cause_summary"), str) else {})