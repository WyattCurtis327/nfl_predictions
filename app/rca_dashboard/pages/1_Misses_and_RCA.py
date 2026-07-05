"""Missed picks and root-cause analysis."""

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

st.set_page_config(
    page_title="Misses & RCA",
    layout="wide",
    page_icon="🔬",
)

VIEW = pick_miss_rca_view()

st.title("Misses & Root Cause Analysis")
st.caption(
    "Review spread and total picks that missed, see how projections stacked up, "
    "and read ranked explanations for each game. "
    "Times shown in America/Los_Angeles as `yyyy-MM-dd_hh_mm`."
)

with st.expander("How to use this page", expanded=False):
    st.markdown(
        """
1. **Pick a season and week** in the sidebar (or leave week as *All weeks* for the full season).
2. Open **Overview** for miss counts and cause charts.
3. Open **Miss board** for a table of every miss; expand a row for the full breakdown.
4. Open **Game explorer** to focus on one matchup at a time.

The **score projection pipeline** chart walks through five stages: play-by-play profiles,
nfelo adjustment, market blend, final simulation, and actual score.
        """
    )

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
def load_misses(
    *,
    season: int,
    week: int | None,
    primary_cause: str | None,
) -> pd.DataFrame:
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
        if pd.isna(value):
            return "—"
    except TypeError:
        pass
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

    narrative = format_narrative(row.to_dict())
    st.info(narrative)

    chart_df = _score_comparison(row)
    st.markdown("**Score projection pipeline**")
    st.bar_chart(chart_df.set_index("stage")[["away", "home"]])

    left, right = st.columns(2)
    with left:
        st.markdown("**Pick context**")
        spread_conf = row.get("spread_confidence")
        if spread_conf is not None and not (isinstance(spread_conf, float) and pd.isna(spread_conf)):
            st.write(
                f"Spread pick: **{row.get('spread_pick', '—')}** ({_format_pct(spread_conf)})"
            )
        else:
            st.write(f"Spread pick: **{row.get('spread_pick', '—')}**")
        total_conf = row.get("total_confidence")
        if total_conf is not None and not (isinstance(total_conf, float) and pd.isna(total_conf)):
            st.write(f"Total pick: **{row.get('total_pick', '—')}** ({_format_pct(total_conf)})")
        else:
            st.write(f"Total pick: **{row.get('total_pick', '—')}**")
        st.write(f"Projection source: `{row.get('projection_source', '—')}`")
        st.write(f"Analyzed at: {format_timestamp_la(row.get('analyzed_at'))}")
    with right:
        st.markdown("**Training & game signals**")
        st.write(
            f"Home profile: {row.get('home_profile_pf_mean', '—')} PF / "
            f"{row.get('home_profile_pa_mean', '—')} PA "
            f"({row.get('home_profile_games', '—')} games, {row.get('profile_source', '—')})"
        )
        st.write(
            f"Away profile: {row.get('away_profile_pf_mean', '—')} PF / "
            f"{row.get('away_profile_pa_mean', '—')} PA "
            f"({row.get('away_profile_games', '—')} games)"
        )
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
        st.markdown("**Ranked root causes**")
        cause_df = pd.DataFrame(causes)
        if "weight" in cause_df.columns:
            cause_df = cause_df.sort_values("weight", ascending=False)
        st.dataframe(
            cause_df[["label", "detail", "weight"]] if "weight" in cause_df.columns else cause_df,
            use_container_width=True,
            hide_index=True,
        )


try:
    seasons_df = load_seasons()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not connect to Databricks SQL: {exc}")
    st.stop()

if seasons_df.empty:
    st.warning(
        "No RCA data yet. After games finish, run the weekly grading job with RCA enabled, "
        "or ask an admin to backfill past seasons."
    )
    st.stop()

with st.sidebar:
    st.header("Filters")
    seasons = sorted(seasons_df["season"].dropna().unique(), reverse=True)
    season = st.selectbox(
        "Season",
        options=seasons,
        index=seasons.index(DEFAULT_SEASON) if DEFAULT_SEASON in seasons else 0,
    )
    season_weeks = load_season_weeks(int(season))
    week_labels = {None: "All weeks"}
    for week_num in season_weeks["week"].tolist():
        week_labels[int(week_num)] = f"Week {int(week_num)}"
    week_choice = st.selectbox(
        "Week",
        options=list(week_labels.keys()),
        format_func=lambda w: week_labels[w],
    )
    cause_summary = load_cause_summary(int(season))
    cause_options: list[str | None] = [None]
    if not cause_summary.empty:
        cause_options.extend(cause_summary["primary_cause"].tolist())
    cause_filter = st.selectbox(
        "Primary cause",
        options=cause_options,
        format_func=lambda c: "All causes" if c is None else c,
    )
    st.divider()
    st.markdown("**Data source**")
    st.code(VIEW, language="sql")

misses = load_misses(season=int(season), week=week_choice, primary_cause=cause_filter)
causes = cause_summary if cause_filter is None else cause_summary[cause_summary["primary_cause"] == cause_filter]

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
        st.subheader("Root causes")
        st.bar_chart(causes.set_index("primary_cause")["misses"])

    cause_week = load_cause_by_week(int(season))
    if not cause_week.empty and week_choice is None:
        st.subheader("Misses by week")
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
        st.dataframe(
            format_timestamps_in_frame(board),
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Details")
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
        )
        game_row = load_game(str(selected))
        if game_row.empty:
            st.warning(f"No RCA row for {selected}")
        else:
            _render_game_card(game_row.iloc[0])