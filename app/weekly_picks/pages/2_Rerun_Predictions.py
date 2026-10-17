"""How to refresh or rerun predictions for the upcoming week."""

from __future__ import annotations

import streamlit as st

from shared import DEFAULT_SEASON, predictions_table

st.set_page_config(page_title="Rerun Predictions", layout="wide", page_icon="🔄")

PREDICTIONS_TABLE = predictions_table()

st.title("Rerun predictions")
st.markdown(
    f"""
This app always shows the **latest prediction run** per game from `{PREDICTIONS_TABLE}`.
Re-running predictions **appends** a new run — you do not need to delete old rows.
Refresh this page after the job finishes to see updated picks.
    """
)

st.header("Before you run")

st.markdown(
    """
1. **Odds must be current** — run `nfl_weekly_refresh` (or at least odds ingest) first.
   Without fresh lines, the predict job may write zero games.
2. **Leave `target_week` blank** in the job to auto-detect the next unplayed week.
3. To target a **specific week**, open notebook `50_predict_upcoming_week` in the
   workspace and set the `target_week` widget instead of using the commands below.
    """
)

st.header("Commands (from your project folder)")

st.markdown("Replace `<your-profile>` with your Databricks CLI profile (e.g. `wyatts_databricks`).")

st.subheader("Production picks only — fastest")
st.markdown("Monte Carlo model only (`monte_carlo`). This is what this app displays today.")
st.code(
    """databricks bundle run nfl_weekly_predictions -t prod --profile <your-profile> --only 00_predict_upcoming_week""",
    language="powershell",
)

st.subheader("All models (shadow stack)")
st.markdown("Monte Carlo plus alternate models and ensemble — does **not** grade last week.")
st.code(
    """databricks bundle run nfl_weekly_predictions -t prod --profile <your-profile> --only 00_predict_upcoming_week,00b_predict_multi_model""",
    language="powershell",
)

st.subheader("Full weekly job")
st.markdown("Predict upcoming week, run all models, **and** grade the latest completed week.")
st.code(
    """databricks bundle run nfl_weekly_predictions -t prod --profile <your-profile>""",
    language="powershell",
)

st.divider()

st.header("What each option does")

st.markdown(
    f"""
| Command | Tasks run | Use when |
|---------|-----------|----------|
| `--only 00_predict_upcoming_week` | Monte Carlo predict | You want updated picks in this app — **usual choice** |
| `--only 00_predict_upcoming_week,00b_predict_multi_model` | All model families | Comparing stack models; see RCA dashboard Model Stack page |
| *(no `--only`)* | Predict + multi-model + grade + schema | End of week housekeeping |

**Season defaults:** jobs use schedule season **{DEFAULT_SEASON}** from bundle variables unless you override notebook parameters.
    """
)

with st.expander("After games finish"):
    st.markdown(
        """
- Grading compares picks to final scores and writes `prediction_grades`.
- RCA for misses runs when `log_rca=true` on the grade notebook (enabled in the full job).
- Open **Misses & RCA** in this app, or the **RCA dashboard**, to review wrong picks.
        """
    )
    st.page_link("pages/1_Misses_and_RCA.py", label="Open Misses & RCA", icon="🔍")

with st.expander("Troubleshooting"):
    st.markdown(
        f"""
**No picks in this app after rerun**

- Confirm odds exist for that week (`nfl.odds` tables).
- Check the predict notebook run in Databricks Workflows for errors.
- Verify you are viewing the correct **season / week** in the sidebar.

**Duplicate or stale picks**

- The app dedupes to the latest `predicted_at` per game. An older run remains in the table but is not shown.
- The run ID shown at the top of the picks page should match the newest job execution.

**Multi-model `model_id` errors**

- Run `python scripts/deploy_mv_game_pick_metrics.py` to add the `model_id` column, or redeploy the bundle.
        """
    )

st.page_link("app.py", label="Back to Weekly Picks", icon="🏈")