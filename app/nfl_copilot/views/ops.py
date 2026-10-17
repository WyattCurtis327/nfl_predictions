"""Operator commands for predictions and grading."""

from __future__ import annotations

import streamlit as st

from shared import DEFAULT_SEASON, predictions_table
from theme import section_header

PREDICTIONS_TABLE = predictions_table()

section_header("Operations", "Refresh data, rerun predictions, and grade completed weeks.")

st.markdown(
    f"""
This workspace reads the **latest prediction run** per game from `{PREDICTIONS_TABLE}`.
Re-running predictions appends a new run — you do not need to delete old rows.
    """
)

tab_run, tab_refresh, tab_grade = st.tabs(["Predict", "Data refresh", "Grade & RCA"])

with tab_run:
    st.markdown("##### Before you run")
    st.markdown(
        """
1. **Odds must be current** — run the weekly refresh (or odds ingest) first.
2. Leave `target_week` blank in the job to auto-detect the next unplayed week.
3. Replace `<your-profile>` with your Databricks CLI profile.
        """
    )
    st.markdown("**Production picks only**")
    st.code(
        "databricks bundle run nfl_weekly_predictions -t prod --profile <your-profile> "
        "--only 00_predict_upcoming_week",
        language="powershell",
    )
    st.markdown("**All models (shadow stack)**")
    st.code(
        "databricks bundle run nfl_weekly_predictions -t prod --profile <your-profile> "
        "--only 00_predict_upcoming_week,00b_predict_multi_model",
        language="powershell",
    )
    st.markdown("**Full weekly job** (predict + grade)")
    st.code(
        "databricks bundle run nfl_weekly_predictions -t prod --profile <your-profile>",
        language="powershell",
    )

with tab_refresh:
    st.markdown("**Full Wednesday pipeline** (odds, PBP, nfelo, then predict)")
    st.code(
        "powershell -ExecutionPolicy Bypass -File scripts/weekly_run.ps1 -Profile <your-profile>",
        language="powershell",
    )
    st.markdown("**Data refresh only**")
    st.code(
        "databricks bundle run nfl_weekly_refresh -t prod --profile <your-profile>",
        language="powershell",
    )

with tab_grade:
    st.markdown(
        f"""
Grading compares picks to final scores and writes RCA rows for misses.
Default season in this app: **{DEFAULT_SEASON}**.

After grading, open **Misses & RCA** to review results.
        """
    )
    st.code(
        "databricks bundle run nfl_weekly_predictions -t prod --profile <your-profile> "
        "--only 01_grade_elapsed_week",
        language="powershell",
    )
    st.markdown("**Backfill RCA for a past season**")
    st.code(
        "python scripts/backfill_prediction_rca.py --season 2025",
        language="powershell",
    )