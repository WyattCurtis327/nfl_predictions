# Databricks notebook source
# MAGIC %md
# MAGIC # RCA agent tools demo
# MAGIC Demonstrates `rca_tools` helpers for a future Databricks Agent or chat UI.
# MAGIC Query `pick_miss_rca`, format narratives, and summarize cause frequencies.

# COMMAND ----------

from nfl_predictions.uc_paths import DEFAULT_CATALOG, DEFAULT_PREDICTIONS_SCHEMA, UcPaths

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("predictions_schema", DEFAULT_PREDICTIONS_SCHEMA, "Predictions schema")
dbutils.widgets.text("season", "2025", "Season")
dbutils.widgets.text("week", "", "Week (blank = all)")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    predictions=dbutils.widgets.get("predictions_schema"),
)
season = int(dbutils.widgets.get("season"))
week_raw = dbutils.widgets.get("week").strip()
week = int(week_raw) if week_raw else None

view = paths.pick_miss_rca_view()
print(f"RCA view: {view}")

# COMMAND ----------

import pandas as pd

from nfl_predictions.rca_tools import format_rca_narrative, get_rca_report, get_weekly_misses, summarize_causes

if not spark.catalog.tableExists(view):
    raise ValueError(f"Deploy {view} first (scripts/deploy_mv_game_pick_metrics.py)")

rca_pdf = spark.table(view).toPandas()
hits = get_weekly_misses(rca_pdf, season=season, week=week)
print(f"Misses: {len(hits)}")
display(spark.createDataFrame(hits))

# COMMAND ----------

summary = summarize_causes(rca_pdf, season=season)
display(spark.createDataFrame(summary))

# COMMAND ----------

if not hits.empty:
    sample = get_rca_report(hits, game_id=str(hits.iloc[0]["game_id"]))
    print(format_rca_narrative(sample))
else:
    print("No misses for the selected filters.")