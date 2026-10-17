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

st.set_page_config(page_title="Model Stack Guide", layout="wide", page_icon="🧩")

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
        "The main production model. Builds team scoring profiles from play-by-play, "
        "blends nfelo power ratings and the sportsbook line, then runs thousands of "
        "simulations to estimate cover and over/under probabilities."
    ),
    "poisson": (
        "Treats each team's expected points as a scoring rate and uses Poisson math "
        "to estimate outcomes. A good independent check on the Monte Carlo simulation."
    ),
    "elo": (
        "Replays completed games to maintain Elo ratings, then translates rating "
        "gaps into projected margins. Captures recent win/loss momentum."
    ),
    "epa_margin": (
        "Uses expected points added (EPA) per play to measure offensive and defensive "
        "efficiency — play quality rather than just final scores."
    ),
    "line_relative": (
        "Learns from past games how often the model edge versus the betting line "
        "predicts covers. Focuses on market-relative value."
    ),
    "shrinkage_profile": (
        "Same profile logic as Monte Carlo, but pulls thin early-season samples toward "
        "league averages so one or two games do not over-influence picks."
    ),
    "situational_total": (
        "Adjusts projected totals for context — division games, dome vs outdoor, "
        "cold weather, wind — then derives over/under probabilities."
    ),
    "ensemble": (
        "Combines all base models using fixed weights (see table below). This is the "
        "candidate “stack pick” once shadow-mode testing shows it beats Monte Carlo alone."
    ),
}

RCA_WEIGHT_HINTS: dict[str, str] = {
    "low_profile_sample": "Favor **Shrunk profiles**; be cautious with Poisson early in the season.",
    "pbp_profile_miss": "Favor **EPA margin** and **Elo**; review whether profiles are stale.",
    "market_calibration": "Favor **Line-relative**; the market blend may be overweighted.",
    "nfelo_adjustment": "Trust **Monte Carlo** nfelo blend; Elo alone may disagree.",
    "turnover_variance": "High randomness — lower confidence; no single model fix.",
    "score_projection_error": "Check **Ensemble** agreement before highlighting a pick.",
}

st.title("Multi-Model Stack")
st.markdown(
    """
Your prediction platform runs **several independent models** each week, then optionally
blends them into an **ensemble** pick. This page explains how the stack works, how it
fits your weekly workflow, and — when grading data is available — how models compare.
    """
)

st.header("At a glance")

c1, c2, c3 = st.columns(3)
with c1:
    st.info(
        "**Production today:** Weekly Picks shows **Monte Carlo** picks (`monte_carlo`). "
        "This is the trusted default until the stack proves itself."
    )
with c2:
    st.info(
        "**Shadow mode:** The weekly job also runs **all models** and stores each under "
        "its own `model_id` in the same predictions table."
    )
with c3:
    st.info(
        "**Your job:** After games finish, grade and review RCA. Use this page to see "
        "whether the **ensemble** is ready to promote."
    )

st.divider()

tab_models, tab_weekly, tab_roadmap, tab_rca, tab_scores = st.tabs(
    ["The models", "Weekly rhythm", "Rollout plan", "RCA + stack", "Live scores"]
)

with tab_models:
    st.subheader("Eight ways we project each game")
    st.caption("Each model writes picks to the same table with a different `model_id`.")

    for model_id, description in MODEL_GUIDE.items():
        label = MODEL_DISPLAY_NAMES.get(model_id, model_id)
        with st.expander(f"**{label}** (`{model_id}`)", expanded=model_id == "monte_carlo"):
            st.markdown(description)

    st.subheader("How the ensemble blends models")
    st.markdown(
        """
The **ensemble** does not replace the base models — it averages their cover and
over/under probabilities using the weights below, then picks the side above the
confidence threshold (default 55%).
        """
    )
    weight_rows = [
        {
            "Model": MODEL_DISPLAY_NAMES.get(mid, mid),
            "model_id": mid,
            "Weight": f"{weight:.0%}",
            "Role": {
                "monte_carlo": "Anchor — nfelo + market calibration",
                "epa_margin": "Play-quality signal",
                "line_relative": "Market inefficiency",
                "poisson": "Independent scoring-rate view",
                "elo": "Recency / momentum",
                "shrinkage_profile": "Early-season stability",
                "situational_total": "Totals context",
            }.get(mid, ""),
        }
        for mid, weight in ENSEMBLE_WEIGHTS.items()
    ]
    st.dataframe(pd.DataFrame(weight_rows), use_container_width=True, hide_index=True)

    st.markdown(
        """
**Spread vs total:** You can route markets differently in the future — for example,
lean on **Situational totals** and **Poisson** for over/under, and **Ensemble** or
**Line-relative** for spreads. That is not automated yet; Monte Carlo handles both today.
        """
    )

with tab_weekly:
    st.subheader("What happens each week")

    st.markdown(
        f"""
| When | What runs | What you see |
|------|-----------|--------------|
| **Before kickoff** | Predict job writes Monte Carlo + all alternate models | **Weekly Picks** app (Monte Carlo only for now) |
| **Games play** | Scores and play-by-play update | Nothing new in RCA yet |
| **After final scores** | Grade job compares every model to results; RCA logs misses | **Misses & RCA** page + leaderboard below |

### Three steps for you

1. **Monday / Tuesday** — Check Weekly Picks for the upcoming week (Monte Carlo).
2. **After the week ends** — Open **Misses & RCA** for what went wrong on production picks.
3. **Same time** — Return here (**Live scores** tab) to compare all models for the season.

### Pick agreement rule (recommended)

Before promoting the ensemble to production, use this simple filter:

- Only treat a pick as a **strong stack play** when **two or more models agree** on the same side **and** ensemble confidence ≥ 55%.
- If models disagree, show the pick as **low conviction** or pass.

RCA only analyzes **misses** today and does not yet tag which `model_id` missed — that is on the roadmap.
        """
    )

    with st.expander("For operators — jobs and tables"):
        st.markdown(
            f"""
| Job / notebook | Purpose |
|----------------|---------|
| `50_predict_upcoming_week` | Production Monte Carlo run |
| `51_predict_multi_model` | All `model_id` values + ensemble (same `prediction_run_id`) |
| `60_grade_elapsed_week` | Grade picks; leave `model_id` **blank** to grade every model |

| Table | Contents |
|-------|----------|
| `{PREDICTIONS_TABLE}` | All model picks (`model_id` column) |
| `{GRADES_TABLE}` | Graded accuracy per model |
            """
        )

with tab_roadmap:
    st.subheader("Rollout plan — four phases")

    phase1, phase2 = st.columns(2)
    with phase1:
        st.markdown("#### Phase 1 — Shadow (now)")
        st.markdown(
            """
- Run all models every week (**already in the job**)
- Grade all models (`model_id` blank in grade notebook)
- **Do not** change what Weekly Picks displays
- Watch the **Live scores** tab on this page
            """
        )
        st.markdown("**Exit criteria:** ≥4 graded weeks; ensemble beats Monte Carlo on high-confidence spreads by ~2pp.")
    with phase2:
        st.markdown("#### Phase 2 — Visibility")
        st.markdown(
            """
- Model picker in **Weekly Picks** (Monte Carlo default)
- “Models agree” indicator on each game
- This guide page (you are here)
            """
        )

    phase3, phase4 = st.columns(2)
    with phase3:
        st.markdown("#### Phase 3 — Smart routing")
        st.markdown(
            """
- Adjust ensemble weights from RCA cause mix (e.g. more shrinkage when `low_profile_sample` dominates)
- Optional: different stack for spread vs total
- Require multi-model agreement for highlighted picks
            """
        )
    with phase4:
        st.markdown("#### Phase 4 — Promote ensemble")
        st.markdown(
            """
- Set Weekly Picks default to **ensemble** when shadow metrics hold
- Keep Monte Carlo as a reference model
- RCA tagged per `model_id` so you know which stack leg failed
            """
        )

    st.warning(
        "Do not auto-tune market or nfelo blends from a single bad week. "
        "Use rolling 4-week RCA cause rates before changing weights."
    )

with tab_rca:
    st.subheader("How RCA helps tune the stack")
    st.markdown(
        """
Root-cause analysis explains **why Monte Carlo missed**. As you compare models on the
**Live scores** tab, use RCA patterns to decide which stack legs to trust more next week.
        """
    )
    st.table(
        [
            {"If RCA shows mostly…": cause.replace("_", " "), "Stack guidance": hint}
            for cause, hint in RCA_WEIGHT_HINTS.items()
        ]
    )
    st.markdown(
        """
**Today:** RCA runs on production grading misses and does not filter by `model_id`.

**Next:** Per-model RCA will show whether ensemble misses are driven by profile error,
market calibration, or random turnover noise — and which alternate model would have hit.

Use **Misses & RCA** alongside this page: RCA tells you *why*; the leaderboard tells you
*who* (which model) is most accurate.
        """
    )
    st.page_link("pages/1_Misses_and_RCA.py", label="Open Misses & RCA", icon="🔬")

with tab_scores:
    st.subheader("Model accuracy leaderboard")
    st.caption(f"From `{GRADES_TABLE}` — spread results excluding pushes.")

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
        st.warning(
            "No graded picks yet. After a completed week, run the grading job with "
            "`model_id` left blank to score every model."
        )
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
        elif board["model_id"].nunique() <= 1:
            st.info(
                "Only one model is graded so far (usually `monte_carlo`). "
                "Run `51_predict_multi_model` before the week, then grade with "
                "`model_id` blank to populate all models."
            )
            display = board.copy()
        else:
            display = board.copy()
            st.success(
                f"Comparing **{display['model_id'].nunique()}** models across "
                f"**{int(display['games_graded'].max())}** graded games (per model)."
            )

        if not display.empty:
            display["Model"] = display["model_id"].map(
                lambda mid: MODEL_DISPLAY_NAMES.get(str(mid), str(mid))
            )
            display["spread_acc_%"] = (display["spread_accuracy"] * 100).round(1)
            display["total_acc_%"] = (display["total_accuracy"] * 100).round(1)
            if display["spread_high_conf_games"].fillna(0).gt(0).any():
                display["high_conf_spread_%"] = (
                    display["spread_high_conf_hits"]
                    / display["spread_high_conf_games"].replace(0, pd.NA)
                    * 100
                ).round(1)
            show_cols = [
                col
                for col in [
                    "Model",
                    "model_id",
                    "games_graded",
                    "spread_acc_%",
                    "total_acc_%",
                    "high_conf_spread_%",
                ]
                if col in display.columns
            ]
            st.dataframe(
                display[show_cols].sort_values("spread_acc_%", ascending=False),
                use_container_width=True,
                hide_index=True,
            )

            if display["model_id"].nunique() > 1:
                chart = display.set_index("Model")[["spread_acc_%", "total_acc_%"]]
                st.bar_chart(chart)

    with st.expander("How to read these numbers"):
        st.markdown(
            """
- **spread_acc_%** — Share of graded spread picks that covered (pushes excluded).
- **total_acc_%** — Same for over/under picks.
- **high_conf_spread_%** — Accuracy only on spreads where confidence was at least 55%.

Monte Carlo is the baseline. If **Ensemble stack** leads on **high_conf_spread_%** for a
full month, it is a candidate to become the Weekly Picks default.
            """
        )

st.divider()
st.page_link("app.py", label="Back to dashboard home", icon="🏠")