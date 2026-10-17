"""Weekly picks board — redesigned card layout."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from display_time import format_timestamp_la, format_timestamps_in_frame
from queries import latest_picks_sql, list_season_weeks_sql
from shared import DEFAULT_SEASON, predictions_table, sql_query, table_has_column
from theme import render_pick_card, section_header


def _format_line(value: float | None, *, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:+.1f}{suffix}" if suffix else f"{value:.1f}"


PREDICTIONS_TABLE = predictions_table()


@st.cache_data(ttl=120)
def load_season_weeks() -> pd.DataFrame:
    return sql_query(list_season_weeks_sql(PREDICTIONS_TABLE))


@st.cache_data(ttl=60)
def load_picks(*, season: int, week: int, has_model_id: bool) -> pd.DataFrame:
    return sql_query(
        latest_picks_sql(
            PREDICTIONS_TABLE,
            season=season,
            week=week,
            has_model_id=has_model_id,
        )
    )


section_header("Weekly Picks", "Monte Carlo spread and total picks from the latest prediction run.")

try:
    season_weeks = load_season_weeks()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load prediction metadata: {exc}")
    st.stop()

if season_weeks.empty:
    st.warning("No predictions found yet. Refresh odds, then rerun predictions from **Operations**.")
    st.stop()

with st.sidebar:
    st.markdown("##### Filters")
    seasons = sorted(season_weeks["season"].dropna().unique(), reverse=True)
    season = st.selectbox(
        "Season",
        options=seasons,
        index=seasons.index(DEFAULT_SEASON) if DEFAULT_SEASON in seasons else 0,
        key="picks_season",
    )
    weeks_for_season = season_weeks[season_weeks["season"] == season]["week"].tolist()
    week = st.selectbox("Week", options=weeks_for_season, index=0, key="picks_week")
    min_confidence = st.slider("Highlight threshold", 0.50, 0.70, 0.55, 0.01, key="picks_conf")
    view_mode = st.radio("Layout", ["Cards", "Table"], horizontal=True, key="picks_layout")

has_model_id = table_has_column(PREDICTIONS_TABLE, "model_id")
picks = load_picks(season=int(season), week=int(week), has_model_id=has_model_id)

if picks.empty:
    st.warning(f"No predictions for season {season}, week {week}.")
    st.stop()

run_id = picks["prediction_run_id"].iloc[0]
predicted_at = format_timestamp_la(picks["predicted_at"].iloc[0])
threshold = (
    float(picks["pick_threshold"].dropna().iloc[0])
    if picks["pick_threshold"].notna().any()
    else 0.55
)
picks = format_timestamps_in_frame(picks)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Games", len(picks))
c2.metric("Spread ≥ threshold", int((picks["spread_confidence"] >= threshold).sum()))
c3.metric("Total ≥ threshold", int((picks["total_confidence"] >= threshold).sum()))
c4.metric("nfelo blend", f"{picks['nfelo_blend'].dropna().iloc[0]:.2f}" if picks["nfelo_blend"].notna().any() else "—")

st.caption(f"Run `{run_id}` · Predicted {predicted_at} LA · Model threshold {threshold:.0%}")

if view_mode == "Table":
    display_cols = [
        "gameday",
        "kickoff_et",
        "away_abbr",
        "home_abbr",
        "spread_pick",
        "spread_confidence",
        "total_pick",
        "total_confidence",
        "away_spread",
        "total_line",
        "proj_away_score",
        "proj_home_score",
        "proj_total",
        "bookmaker",
    ]
    table = picks[display_cols].copy()
    table["spread_confidence"] = table["spread_confidence"].map(
        lambda v: f"{v:.0%}" if pd.notna(v) else "—"
    )
    table["total_confidence"] = table["total_confidence"].map(
        lambda v: f"{v:.0%}" if pd.notna(v) else "—"
    )
    st.dataframe(table, use_container_width=True, hide_index=True)
else:
    hot_first = picks.copy()
    hot_first["_hot"] = hot_first.apply(
        lambda row: (
            (pd.notna(row["spread_confidence"]) and row["spread_confidence"] >= min_confidence)
            or (pd.notna(row["total_confidence"]) and row["total_confidence"] >= min_confidence)
        ),
        axis=1,
    )
    hot_first = hot_first.sort_values("_hot", ascending=False)
    for _, row in hot_first.iterrows():
        render_pick_card(row, min_confidence=min_confidence, format_line=_format_line)