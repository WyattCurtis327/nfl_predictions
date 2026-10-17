# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest nflverse rosters
# MAGIC Loads current-season roster snapshot into `nfl.landing.rosters`.

# COMMAND ----------

from nfl_predictions.uc_paths import DEFAULT_CATALOG, DEFAULT_ROSTERS_SCHEMA, UcPaths

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("rosters_schema", DEFAULT_ROSTERS_SCHEMA, "Rosters schema")
dbutils.widgets.text("roster_season", "2026", "Roster season")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    rosters=dbutils.widgets.get("rosters_schema"),
)
roster_season = int(dbutils.widgets.get("roster_season"))
rosters_table = paths.rosters_table()

# COMMAND ----------

from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.nflverse_data import NFLVERSE_ROSTER_URL, fetch_rosters
from nfl_predictions.spark_io import write_delta_table

rosters_df = fetch_rosters(roster_season)
rosters_pdf = stamp_dataframe(
    rosters_df,
    source_file=NFLVERSE_ROSTER_URL.format(season=roster_season),
)

print(f"Rosters {roster_season}: {len(rosters_pdf):,} rows")

# COMMAND ----------

roster_keys = [key for key in ("gsis_id", "week", "team") if key in rosters_pdf.columns]
write_delta_table(spark, rosters_pdf, rosters_table, dedupe_keys=roster_keys or None)

display(spark.table(rosters_table).groupBy("team").count().orderBy("team"))