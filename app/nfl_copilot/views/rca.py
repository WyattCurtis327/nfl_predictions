"""Misses and root-cause analysis — redesigned."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from display_time import format_timestamp_la, format_timestamps_in_frame
from queries import (
    cause_by_week_sql,
    cause_summary_sql,
    format_narrative,
    game_detail_sql,
    list_rca_season_weeks_sql,
    list_rca_seasons_sql,
    missed_picks_sql,
    parse_causes,
)
from shared import DEFAULT_SEASON, pick_miss_rca_view, sql_query
from theme import render_narrative, section_header

VIEW = pick_miss_rca_view()


@st.cache_data(ttl=180)
def load_seasons() -> pd.DataFrame:
    return sql_query(list_rca_seasons_sql(VIEW))


@st.cache_data(ttl=120)
def load_season_weeks(season: int) -> pd.DataFrame:
    return sql_query(list_rca_season_weeks_sql(VIEW, season=season))


@st.cache_data(ttl=120)
def load_cause_summary(season: int) -> pd.DataFrame:
    return sql_query(cause_summary_sql(VIEW, season=season))


@st.cache_data(ttl=120)
def load_cause_by_week(season: int) -> pd.DataFrame:
    return sql_query(cause_by_week_sql(VIEW, season=season))


@st.cache_data(ttl=60)
def load_misses(*, season: int, week: int | None, primary_cause: str | None) -> pd.DataFrame:
    return sql_query(
        missed_picks_sql(VIEW, season=season, week=week, primary_cause=primary_cause)
    )


@st.cache_data(ttl=60)
def load_game(game_id: str) -> pd.DataFrame:
    return sql_query(game_detail_sql(VIEW, game_id=game_id))


def _format_pct(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "—"
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return str(value)


def _score_comparison(row: pd.Series) -> pd.DataFrame:
    stages = ["PBP", "nfelo", "Market", "Sim", "Actual"]
    away_cols = [
        "pbp_proj_away",
        "nfelo_proj_away",
        "market_proj_away",
        "proj_away_score",
        "actual_away_score",
    ]
    home_cols = [
        "pbp_proj_home",
        "nfelo_proj_home",
        "market_proj_home",
        "proj_home_score",
        "actual_home_score",
    ]
    return pd.DataFrame(
        {
            "stage": stages,
            "away": [row.get(col) for col in away_cols],
            "home": [row.get(col) for col in home_cols],
        }
    )


def _render_game_card(row: pd.Series) -> None:
    st.markdown(f"### {row['away_abbr']} @ {row['home_abbr']}")
    st.caption(
        f"Week {row['week']} · {format_timestamp_la(row.get('gameday'))} · "
        f"missed **{row['miss_types']}** · `{row['primary_cause']}`"
    )
    render_narrative(format_narrative(row.to_dict()))

    chart_df = _score_comparison(row)
    st.markdown("**Score projection pipeline**")
    st.bar_chart(chart_df.set_index("stage")[["away", "home"]], color=["#5b9cf5", "#2dd4a8"])

    left, right = st.columns(2)
    with left:
        st.markdown("**Pick context**")
        st.write(
            f"Spread: **{row.get('spread_pick', '—')}** ({_format_pct(row.get('spread_confidence'))})"
        )
        st.write(f"Total: **{row.get('total_pick', '—')}** ({_format_pct(row.get('total_confidence'))})")
        st.write(f"Source: `{row.get('projection_source', '—')}`")
    with right:
        st.markdown("**Game signals**")
        st.write(
            f"Turnovers: {row['away_abbr']} {row.get('game_away_turnovers', '—')}, "
            f"{row['home_abbr']} {row.get('game_home_turnovers', '—')}"
        )
        if pd.notna(row.get("game_home_epa")):
            st.write(
                f"EPA: {row['away_abbr']} {row.get('game_away_epa', '—')}, "
                f"{row['home_abbr']} {row.get('game_home_epa', '—')}"
            )

    causes = parse_causes(row.get("cause_summary"))
    if causes:
        cause_df = pd.DataFrame(causes)
        if "weight" in cause_df.columns:
            cause_df = cause_df.sort_values("weight", ascending=False)
        st.dataframe(
            cause_df[["label", "detail", "weight"]] if "weight" in cause_df.columns else cause_df,
            use_container_width=True,
            hide_index=True,
        )


section_header(
    "Misses & RCA",
    "Spread and total picks that missed, with deterministic root-cause decomposition.",
)

try:
    seasons_df = load_seasons()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not connect to Databricks SQL: {exc}")
    st.stop()

if seasons_df.empty:
    st.warning("No RCA data yet. Grade a completed week with RCA enabled, or backfill past seasons.")
    st.stop()

with st.sidebar:
    st.markdown("##### Filters")
    seasons = sorted(seasons_df["season"].dropna().unique(), reverse=True)
    season = st.selectbox(
        "Season",
        options=seasons,
        index=seasons.index(DEFAULT_SEASON) if DEFAULT_SEASON in seasons else 0,
        key="rca_season",
    )
    season_weeks = load_season_weeks(int(season))
    week_labels = {None: "All weeks"}
    for week_num in season_weeks["week"].tolist():
        week_labels[int(week_num)] = f"Week {int(week_num)}"
    week_choice = st.selectbox(
        "Week",
        options=list(week_labels.keys()),
        format_func=lambda w: week_labels[w],
        key="rca_week",
    )
    cause_summary = load_cause_summary(int(season))
    cause_options: list[str | None] = [None]
    if not cause_summary.empty:
        cause_options.extend(cause_summary["primary_cause"].tolist())
    cause_filter = st.selectbox(
        "Primary cause",
        options=cause_options,
        format_func=lambda c: "All causes" if c is None else c,
        key="rca_cause",
    )

misses = load_misses(season=int(season), week=week_choice, primary_cause=cause_filter)
causes = (
    cause_summary
    if cause_filter is None
    else cause_summary[cause_summary["primary_cause"] == cause_filter]
)

tab_overview, tab_week, tab_game = st.tabs(["Overview", "Miss board", "Game explorer"])

with tab_overview:
    c1, c2, c3 = st.columns(3)
    c1.metric("Total misses", len(misses))
    c2.metric(
        "Spread misses",
        int(misses["miss_types"].astype(str).str.contains("spread").sum()) if not misses.empty else 0,
    )
    c3.metric(
        "Total misses (O/U)",
        int(misses["miss_types"].astype(str).str.contains("total").sum()) if not misses.empty else 0,
    )
    if not causes.empty:
        st.markdown("**Root causes**")
        st.bar_chart(causes.set_index("primary_cause")["misses"], color="#f07178")
    cause_week = load_cause_by_week(int(season))
    if not cause_week.empty and week_choice is None:
        st.markdown("**Misses by week**")
        pivot = cause_week.pivot_table(
            index="week", columns="primary_cause", values="misses", fill_value=0
        )
        st.bar_chart(pivot)

with tab_week:
    if misses.empty:
        st.success("No misses match the current filters.")
    else:
        board = misses[
            [
                "week",
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
        ].copy()
        st.dataframe(format_timestamps_in_frame(board), use_container_width=True, hide_index=True)
        for _, row in misses.iterrows():
            with st.expander(f"{row['away_abbr']} @ {row['home_abbr']} — {row['primary_cause']}"):
                _render_game_card(row)

with tab_game:
    if misses.empty:
        st.info("Select a season/week with misses to explore games.")
    else:
        game_labels = {
            str(row["game_id"]): (
                f"{row['away_abbr']} @ {row['home_abbr']} (wk {row['week']}) — {row['primary_cause']}"
            )
            for _, row in misses.iterrows()
        }
        selected = st.selectbox(
            "Game",
            options=list(game_labels.keys()),
            format_func=lambda gid: game_labels[gid],
            key="rca_game",
        )
        game_row = load_game(str(selected))
        if game_row.empty:
            st.warning(f"No RCA row for {selected}")
        else:
            _render_game_card(game_row.iloc[0])