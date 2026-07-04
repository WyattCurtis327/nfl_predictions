# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest nflverse odds from schedules
# MAGIC Extracts closing lines embedded in `nfl.schedules.games` into `nfl.odds.*`.

# COMMAND ----------

from nfl_predictions.uc_paths import (
    DEFAULT_CATALOG,
    DEFAULT_ODDS_SCHEMA,
    DEFAULT_SCHEDULES_SCHEMA,
    UcPaths,
)

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("odds_schema", DEFAULT_ODDS_SCHEMA, "Odds schema")
dbutils.widgets.text("schedules_schema", DEFAULT_SCHEDULES_SCHEMA, "Schedules schema")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    odds=dbutils.widgets.get("odds_schema"),
    schedules=dbutils.widgets.get("schedules_schema"),
)
games_table = paths.schedules_games_table()
game_odds_table = paths.game_odds_table()
odds_lines_table = paths.odds_lines_table()
latest_table = paths.game_odds_latest_table()
gaps_table = paths.odds_ingest_gaps_table()

# COMMAND ----------

from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.odds import (
    GAME_ODDS_KEY,
    ODDS_GAPS_KEY,
    ODDS_LINES_KEY,
    build_odds_from_schedule,
    nflverse_odds_source_file,
)
from nfl_predictions.spark_io import write_delta_table

if not spark.catalog.tableExists(games_table):
    raise ValueError(f"Schedule table {games_table} must exist before ingesting odds")

schedule_pdf = spark.table(games_table).dropDuplicates(["game_id"]).toPandas()
source_file = nflverse_odds_source_file()

game_odds_df, odds_lines_df, latest_df, gaps_df = build_odds_from_schedule(schedule_pdf)

game_odds_pdf = stamp_dataframe(game_odds_df, source_file=source_file)
odds_lines_pdf = stamp_dataframe(odds_lines_df, source_file=source_file)
latest_pdf = stamp_dataframe(latest_df, source_file=source_file)
gaps_pdf = stamp_dataframe(gaps_df, source_file=source_file)

print(f"scheduled games: {len(schedule_pdf):,}")
print(f"game_odds: {len(game_odds_pdf):,}")
print(f"odds_lines: {len(odds_lines_pdf):,}")
print(f"game_odds_latest: {len(latest_pdf):,}")
print(f"odds_ingest_gaps: {len(gaps_pdf):,}")

# COMMAND ----------

table_specs = [
    (game_odds_pdf, game_odds_table, GAME_ODDS_KEY),
    (odds_lines_pdf, odds_lines_table, ODDS_LINES_KEY),
    (latest_pdf, latest_table, GAME_ODDS_KEY),
    (gaps_pdf, gaps_table, ODDS_GAPS_KEY),
]
for pdf, table, dedupe_keys in table_specs:
    write_delta_table(spark, pdf, table, dedupe_keys=dedupe_keys)

display(
    spark.table(game_odds_table)
    .groupBy("season", "game_type")
    .count()
    .orderBy("season", "game_type")
)