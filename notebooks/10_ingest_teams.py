# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest nflverse teams
# MAGIC Loads team reference data into `nfl.landing.teams`.

# COMMAND ----------

from nfl_predictions.uc_paths import DEFAULT_CATALOG, DEFAULT_TEAMS_SCHEMA, UcPaths

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("teams_schema", DEFAULT_TEAMS_SCHEMA, "Teams schema")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    teams=dbutils.widgets.get("teams_schema"),
)
teams_table = paths.teams_table()

# COMMAND ----------

from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.nflverse_data import NFLVERSE_TEAMS_URL, fetch_teams
from nfl_predictions.spark_io import write_delta_table

teams_df = fetch_teams()
teams_pdf = stamp_dataframe(teams_df, source_file=NFLVERSE_TEAMS_URL)

print(f"Teams: {len(teams_pdf):,} rows")

# COMMAND ----------

team_keys = [key for key in ("team", "season") if key in teams_pdf.columns] or ["team_abbr", "season"]
write_delta_table(spark, teams_pdf, teams_table, dedupe_keys=team_keys)

display(spark.table(teams_table).orderBy("team"))