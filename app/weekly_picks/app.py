"""Read-only Streamlit dashboard for latest weekly NFL model picks."""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from databricks import sql
from databricks.sdk.core import Config

from queries import latest_picks_sql, list_season_weeks_sql, predictions_table

st.set_page_config(page_title="NFL Weekly Picks", layout="wide", page_icon="🏈")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


CATALOG = _env("NFL_CATALOG", "nfl")
PREDICTIONS_SCHEMA = _env("NFL_PREDICTIONS_SCHEMA", "predictions")
DEFAULT_SEASON = int(_env("NFL_SCHEDULE_SEASON", "2026"))
PREDICTIONS_TABLE = predictions_table(CATALOG, PREDICTIONS_SCHEMA)


def _warehouse_id_from_app_resources() -> str:
    app_name = _env("DATABRICKS_APP_NAME")
    if not app_name:
        return ""
    from databricks.sdk import WorkspaceClient

    app = WorkspaceClient().apps.get(app_name)
    for resource in app.resources or []:
        if resource.sql_warehouse and resource.sql_warehouse.id:
            return str(resource.sql_warehouse.id).strip()
    return ""


@st.cache_resource
def _warehouse_id() -> str:
    warehouse_id = _env("DATABRICKS_WAREHOUSE_ID") or _warehouse_id_from_app_resources()
    if not warehouse_id:
        st.error(
            "DATABRICKS_WAREHOUSE_ID is not set. Attach a SQL warehouse app resource "
            "named `sql-warehouse` and redeploy the bundle."
        )
        st.stop()
    return warehouse_id


def sql_query(query: str) -> pd.DataFrame:
    cfg = Config()
    with sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{_warehouse_id()}",
        credentials_provider=lambda: cfg.authenticate,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall_arrow().to_pandas()


@st.cache_data(ttl=120)
def load_season_weeks() -> pd.DataFrame:
    return sql_query(list_season_weeks_sql(PREDICTIONS_TABLE))


@st.cache_data(ttl=60)
def load_picks(*, season: int, week: int) -> pd.DataFrame:
    return sql_query(latest_picks_sql(PREDICTIONS_TABLE, season=season, week=week))


def _matchup_label(row: pd.Series) -> str:
    return f"{row['away_abbr']} @ {row['home_abbr']}"


def _format_line(value: float | None, *, suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:+.1f}{suffix}" if suffix else f"{value:.1f}"


st.title("NFL Weekly Picks")
st.caption(
    f"Latest model spread and total picks from `{PREDICTIONS_TABLE}` "
    "(one row per game from the most recent prediction run)."
)

try:
    season_weeks = load_season_weeks()
except Exception as exc:  # noqa: BLE001 - surface connection errors in UI
    st.error(f"Could not load prediction metadata: {exc}")
    st.stop()

if season_weeks.empty:
    st.warning("No predictions found yet. Run `nfl_weekly_predictions` after refreshing odds.")
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
    min_confidence = st.slider("Min confidence to highlight", 0.50, 0.70, 0.55, 0.01)
    st.divider()
    st.markdown("**Source**")
    st.code(PREDICTIONS_TABLE, language="sql")

picks = load_picks(season=int(season), week=int(week))
if picks.empty:
    st.warning(f"No predictions for season {season}, week {week}.")
    st.stop()

run_id = picks["prediction_run_id"].iloc[0]
predicted_at = picks["predicted_at"].iloc[0]
threshold = float(picks["pick_threshold"].dropna().iloc[0]) if picks["pick_threshold"].notna().any() else 0.55

col1, col2, col3, col4 = st.columns(4)
col1.metric("Games", len(picks))
col2.metric(
    "Spread picks ≥ threshold",
    int((picks["spread_confidence"] >= threshold).sum()),
)
col3.metric(
    "Total picks ≥ threshold",
    int((picks["total_confidence"] >= threshold).sum()),
)
col4.metric("nfelo blend", f"{picks['nfelo_blend'].dropna().iloc[0]:.2f}" if picks["nfelo_blend"].notna().any() else "—")

st.markdown(
    f"**Run:** `{run_id}`  \n"
    f"**Predicted at:** {predicted_at}  \n"
    f"**Pick threshold (model):** {threshold:.0%}"
)

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
table["spread_confidence"] = table["spread_confidence"].map(lambda v: f"{v:.0%}" if pd.notna(v) else "—")
table["total_confidence"] = table["total_confidence"].map(lambda v: f"{v:.0%}" if pd.notna(v) else "—")

st.subheader("Pick board")
st.dataframe(table, use_container_width=True, hide_index=True)

st.subheader("Game detail")
for _, row in picks.iterrows():
    spread_flag = row["spread_confidence"] >= min_confidence if pd.notna(row["spread_confidence"]) else False
    total_flag = row["total_confidence"] >= min_confidence if pd.notna(row["total_confidence"]) else False
    title = _matchup_label(row)
    if spread_flag or total_flag:
        title = f"⭐ {title}"
    with st.expander(title):
        left, right = st.columns(2)
        with left:
            st.markdown("**Spread**")
            st.write(f"Pick: **{row['spread_pick'] or '—'}** ({row['spread_confidence']:.0%})" if pd.notna(row["spread_confidence"]) else f"Pick: **{row['spread_pick'] or '—'}**")
            st.write(f"Line: away {_format_line(row['away_spread'])}, home {_format_line(row['home_spread'])}")
            st.write(f"Projected: {row['proj_away_score']:.1f} – {row['proj_home_score']:.1f}")
        with right:
            st.markdown("**Total**")
            st.write(f"Pick: **{row['total_pick'] or '—'}** ({row['total_confidence']:.0%})" if pd.notna(row["total_confidence"]) else f"Pick: **{row['total_pick'] or '—'}**")
            st.write(f"Line: {_format_line(row['total_line'])}")
            st.write(f"Projected total: {_format_line(row['proj_total'])}")