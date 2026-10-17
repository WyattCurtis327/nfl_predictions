# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest nflverse schedules
# MAGIC Merges REG + playoff games into `nfl.landing.games` (preseason excluded).

# COMMAND ----------

from nfl_predictions.uc_paths import DEFAULT_CATALOG, DEFAULT_SCHEDULES_SCHEMA, UcPaths

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("schedules_schema", DEFAULT_SCHEDULES_SCHEMA, "Schedules schema")
dbutils.widgets.text("schedule_seasons", "2024,2025,2026", "Comma-separated seasons")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    schedules=dbutils.widgets.get("schedules_schema"),
)
schedule_seasons_raw = dbutils.widgets.get("schedule_seasons")
games_table = paths.schedules_games_table()

# COMMAND ----------

from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.nflverse_data import (
    GAME_TYPES_REG_PLAYOFF,
    NFLVERSE_GAMES_URL,
    fetch_season_schedule,
    merge_schedule_season,
    parse_season_list,
)
from nfl_predictions.spark_io import dedupe_pandas, write_delta_table

seasons = parse_season_list(schedule_seasons_raw)
if not seasons:
    raise ValueError("schedule_seasons must list at least one season")

schedule_pdf = None
for season in seasons:
    season_df = fetch_season_schedule(season, game_types=GAME_TYPES_REG_PLAYOFF)
    season_pdf = stamp_dataframe(
        season_df,
        source_file=f"{NFLVERSE_GAMES_URL}#season={season}",
    )
    if schedule_pdf is None:
        schedule_pdf = season_pdf
    else:
        schedule_pdf = merge_schedule_season(schedule_pdf, season_pdf, season)

print(
    f"Schedule merge for seasons {seasons}: {len(schedule_pdf):,} rows, "
    f"game types {sorted(schedule_pdf['game_type'].dropna().unique().tolist())}"
)

# COMMAND ----------

schedule_pdf = dedupe_pandas(schedule_pdf, ["game_id"])
write_delta_table(spark, schedule_pdf, games_table, dedupe_keys=["game_id"])

display(
    spark.table(games_table)
    .groupBy("season", "game_type")
    .count()
    .orderBy("season", "game_type")
)