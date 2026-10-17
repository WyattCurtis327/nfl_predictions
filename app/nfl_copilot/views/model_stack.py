"""Multi-model prediction stack — guidance and live comparison."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from queries import MODEL_DISPLAY_NAMES, list_graded_seasons_sql, model_leaderboard_sql
from shared import (
    DEFAULT_SEASON,
    game_predictions_table,
    prediction_grades_table,
    sql_query,
    table_has_column,
)
from theme import section_header

GRADES_TABLE = prediction_grades_table()
PREDICTIONS_TABLE = game_predictions_table()

ENSEMBLE_WEIGHTS: dict[str, float] = {
    "monte_carlo": 0.30,
    "poisson": 0.10,
    "elo": 0.10,
    "epa_margin": 0.15,
    "line_relative": 0.15,
    "shrinkage_profile": 0.10,
    "situational_total": 0.10,
}

MODEL_GUIDE: dict[str, str] = {
    "monte_carlo": (
        "Production anchor — PBP profiles, nfelo blend, market calibration, Monte Carlo simulation."
    ),
    "poisson": "Independent scoring-rate view using Poisson math on expected points.",
    "elo": "Rating gaps from replayed game results — captures recent momentum.",
    "epa_margin": "Play-quality signal from expected points added per play.",
    "line_relative": "Market-relative edge — how often model vs line predicts covers.",
    "shrinkage_profile": "PBP profiles shrunk toward league average for thin samples.",
    "situational_total": "Totals adjusted for division games, weather, dome, wind.",
    "ensemble": "Weighted blend of all base models — candidate production pick once proven.",
}

RCA_WEIGHT_HINTS: dict[str, str] = {
    "low_profile_sample": "Favor shrunk profiles; be cautious with Poisson early season.",
    "pbp_profile_miss": "Favor EPA margin and Elo; check whether profiles are stale.",
    "market_calibration": "Favor line-relative; market blend may be overweighted.",
    "nfelo_adjustment": "Trust Monte Carlo nfelo blend.",
    "turnover_variance": "High randomness — lower confidence.",
    "score_projection_error": "Check ensemble agreement before highlighting.",
}

section_header(
    "Model Stack",
    "Shadow models, ensemble weights, rollout plan, and live accuracy when grades exist.",
)

c1, c2, c3 = st.columns(3)
c1.info("**Production:** Monte Carlo (`monte_carlo`) powers the pick board.")
c2.info("**Shadow:** Weekly job writes every `model_id` to the same predictions table.")
c3.info("**Goal:** Promote ensemble when leaderboard + RCA support it.")

tab_models, tab_weekly, tab_roadmap, tab_rca, tab_scores = st.tabs(
    ["Models", "Weekly rhythm", "Rollout", "RCA tuning", "Leaderboard"]
)

with tab_models:
    for model_id, description in MODEL_GUIDE.items():
        label = MODEL_DISPLAY_NAMES.get(model_id, model_id)
        with st.expander(f"{label} · `{model_id}`", expanded=model_id == "monte_carlo"):
            st.markdown(description)

    weight_rows = [
        {
            "Model": MODEL_DISPLAY_NAMES.get(mid, mid),
            "Weight": f"{weight:.0%}",
            "Role": {
                "monte_carlo": "Anchor",
                "epa_margin": "Play quality",
                "line_relative": "Market edge",
                "poisson": "Scoring rate",
                "elo": "Momentum",
                "shrinkage_profile": "Early season",
                "situational_total": "Totals context",
            }.get(mid, ""),
        }
        for mid, weight in ENSEMBLE_WEIGHTS.items()
    ]
    st.dataframe(pd.DataFrame(weight_rows), use_container_width=True, hide_index=True)

with tab_weekly:
    st.markdown(
        """
| Phase | Action |
|-------|--------|
| Pre-kickoff | Check **Picks** for Monte Carlo lines |
| Post-week | Review **Misses & RCA** |
| Same time | Compare models on **Leaderboard** tab |
        """
    )

with tab_roadmap:
    p1, p2 = st.columns(2)
    with p1:
        st.markdown("**Phase 1 — Shadow (now)**")
        st.markdown("Run + grade all models; keep Monte Carlo as default display.")
    with p2:
        st.markdown("**Phase 2 — Visibility**")
        st.markdown("Model picker and agreement indicators on pick cards.")
    p3, p4 = st.columns(2)
    with p3:
        st.markdown("**Phase 3 — Smart routing**")
        st.markdown("Tune ensemble weights from RCA cause mix.")
    with p4:
        st.markdown("**Phase 4 — Promote ensemble**")
        st.markdown("Switch default when shadow metrics hold 4+ weeks.")

with tab_rca:
    st.table(
        [
            {"RCA pattern": cause.replace("_", " "), "Stack guidance": hint}
            for cause, hint in RCA_WEIGHT_HINTS.items()
        ]
    )

with tab_scores:
    @st.cache_data(ttl=120)
    def load_graded_seasons() -> pd.DataFrame:
        return sql_query(list_graded_seasons_sql(GRADES_TABLE))

    grades_have_model_id = table_has_column(GRADES_TABLE, "model_id")

    @st.cache_data(ttl=120)
    def load_leaderboard(season: int, *, has_model_id: bool) -> pd.DataFrame:
        return sql_query(
            model_leaderboard_sql(GRADES_TABLE, season=season, has_model_id=has_model_id)
        )

    try:
        seasons_df = load_graded_seasons()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not load grades: {exc}")
        st.stop()

    if seasons_df.empty:
        st.warning("No graded picks yet. Run the grading job after a completed week.")
    else:
        seasons = sorted(seasons_df["season"].dropna().unique(), reverse=True)
        season = st.selectbox(
            "Season",
            options=seasons,
            index=seasons.index(DEFAULT_SEASON) if DEFAULT_SEASON in seasons else 0,
            key="stack_season",
        )
        board = load_leaderboard(int(season), has_model_id=grades_have_model_id)
        if board.empty:
            st.info("No spread grades for this season yet.")
        else:
            display = board.copy()
            display["Model"] = display["model_id"].map(
                lambda mid: MODEL_DISPLAY_NAMES.get(str(mid), str(mid))
            )
            display["spread_acc_%"] = (display["spread_accuracy"] * 100).round(1)
            display["total_acc_%"] = (display["total_accuracy"] * 100).round(1)
            st.dataframe(
                display[
                    ["Model", "model_id", "games_graded", "spread_acc_%", "total_acc_%"]
                ].sort_values("spread_acc_%", ascending=False),
                use_container_width=True,
                hide_index=True,
            )
            if display["model_id"].nunique() > 1:
                st.bar_chart(display.set_index("Model")[["spread_acc_%", "total_acc_%"]])