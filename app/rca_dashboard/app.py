"""NFL RCA dashboard — intro and navigation."""

from __future__ import annotations

import streamlit as st

from shared import DEFAULT_SEASON, pick_miss_rca_view

st.set_page_config(
    page_title="NFL RCA Dashboard",
    layout="wide",
    page_icon="🏈",
)

st.title("NFL Predictions — RCA Dashboard")
st.markdown(
    """
Welcome. This app helps you **understand why picks missed** after games are played,
and **compare team strength** from play-by-play scoring data.

Use the sidebar to switch pages, or jump directly below.
    """
)

nav1, nav2 = st.columns(2)

with nav1:
    st.subheader("Misses & RCA")
    st.markdown(
        """
Investigate spread and over/under picks that did not cover.

- Season and week filters
- Charts of the most common miss reasons
- Per-game score pipeline (profiles → nfelo → market → simulation → actual)
- Plain-language narrative for each miss
        """
    )
    st.page_link("pages/1_Misses_and_RCA.py", label="Open Misses & RCA", icon="🔬")

with nav2:
    st.subheader("Team Ratings")
    st.markdown(
        """
Scatter plot of **net offensive** vs **net defensive** team ratings.

- Built from final scores in play-by-play data
- Filter by season and one or more weeks
- League-average teams sit near (0, 0)
        """
    )
    st.page_link("pages/2_Team_Ratings.py", label="Open Team Ratings", icon="📊")

st.divider()

st.header("Quick start")

st.markdown(
    f"""
### During the season (typical week)

1. **Before kickoff** — Weekly picks are published in the **NFL Weekly Picks** app
   (Monte Carlo model). No RCA exists yet because games have not been played.
2. **After games finish** — The `nfl_weekly_predictions` job grades results and,
   when enabled, writes root-cause rows for every miss.
3. **Review here** — Open **Misses & RCA**, choose season **{DEFAULT_SEASON}** (or the
   year you care about), pick the week, and read the Overview tab first.

RCA only includes **incorrect** spread or total picks. Winning weeks may show few or
no rows — that is expected.
    """
)

st.header("Understanding root causes")

st.markdown(
    """
Each miss gets a **primary cause** (the strongest explanation) plus a ranked list of
contributing factors. Common labels you will see:
    """
)

cause_help = {
    "pbp_profile_miss": "Team scoring profiles from past games did not match how teams actually scored.",
    "nfelo_adjustment": "The nfelo power-rating blend shifted the projection away from the final score.",
    "market_calibration": "Blending toward the betting line moved the pick in the wrong direction.",
    "score_projection_error": "The final simulated scores were off compared with the actual result.",
    "low_profile_sample": "One or both teams had few games in the training window, so profiles were unreliable.",
    "turnover_variance": "Turnovers in the game swung the margin or total more than the model expected.",
    "single_game_profile_swing": "Including this game would have materially changed a team's profile.",
}

st.table(
    [{"Cause": key.replace("_", " "), "What it means": desc} for key, desc in cause_help.items()]
)

st.header("Score projection pipeline")

st.markdown(
    """
When you open a game, the bar chart shows five checkpoints for each team:

| Stage | Meaning |
|-------|---------|
| **PBP** | Expected points from play-by-play scoring profiles |
| **nfelo** | After blending nfelo power ratings |
| **Market** | After blending toward the sportsbook line |
| **Sim** | Final Monte Carlo projection used for the pick |
| **Actual** | Real final score |

Large jumps between stages show where the model diverged from reality.
    """
)

with st.expander("For operators — how data gets here"):
    st.markdown(
        f"""
**Predictions** land in `nfl.predictions.game_predictions` (see Weekly Picks app).

**Grading** compares picks to final scores and writes `nfl.predictions.prediction_grades`.

**RCA** runs during grading when `log_rca=true` and fills `nfl.predictions.prediction_rca`.
This dashboard reads the view **`{pick_miss_rca_view()}`**, which exposes misses only.

If a season looks empty:

- Confirm games were graded after scores were final.
- For historical seasons, an admin can run
  `python scripts/backfill_prediction_rca.py --season <year>`.

**Team Ratings** reads play-by-play directly (`nfl.pbp.play_by_play`) and does not depend
on RCA being populated.
        """
    )

with st.expander("Tips"):
    st.markdown(
        """
- Start with **Overview** and filter **Primary cause** to spot recurring patterns across a season.
- Use **Game explorer** when you want one matchup without scrolling the full miss board.
- **Team Ratings** is useful pre-game too — it shows offensive/defensive form for any completed week window.
- RCA explains past picks; it does **not** change future predictions automatically. Fresh PBP and
  odds ingests are what update the model inputs for the next week.
        """
    )