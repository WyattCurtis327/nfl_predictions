# Databricks notebook source
# MAGIC %md
# MAGIC # Load PBP from UC Volume
# MAGIC Reads volume parquet into `nfl.pbp.play_by_play`.
# MAGIC Drops preseason, joins `schedules.games` for `game_type`, and keeps REG + playoffs only.

# COMMAND ----------

from nfl_predictions.uc_paths import DEFAULT_CATALOG, DEFAULT_PBP_SCHEMA, DEFAULT_SCHEDULES_SCHEMA, UcPaths

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("pbp_schema", DEFAULT_PBP_SCHEMA, "PBP schema")
dbutils.widgets.text("schedules_schema", DEFAULT_SCHEDULES_SCHEMA, "Schedules schema")
dbutils.widgets.text("pbp_seasons", "2024,2025", "Comma-separated seasons")
dbutils.widgets.text("pbp_volume", "", "UC Volume path")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    pbp=dbutils.widgets.get("pbp_schema"),
    schedules=dbutils.widgets.get("schedules_schema"),
)
pbp_seasons_raw = dbutils.widgets.get("pbp_seasons")
pbp_volume = dbutils.widgets.get("pbp_volume").strip() or paths.pbp_volume()

pbp_table = paths.pbp_table()
games_table = paths.schedules_games_table()

# COMMAND ----------

from datetime import datetime, timezone

from pyspark.sql import functions as F

from nfl_predictions.metadata import utc_now
from nfl_predictions.nflverse_data import GAME_TYPES_REG_PLAYOFF, parse_season_list
from nfl_predictions.pbp_volume import pbp_parquet_path, read_volume_parquet
from nfl_predictions.spark_io import union_by_name_harmonized

seasons = parse_season_list(pbp_seasons_raw)
if not seasons:
    raise ValueError("pbp_seasons must list at least one season")

if not spark.catalog.tableExists(games_table):
    raise RuntimeError(f"Schedule table required before PBP load: {games_table}")

ingested_at = utc_now()
game_types = list(GAME_TYPES_REG_PLAYOFF)

schedule_df = (
    spark.table(games_table)
    .select("game_id", "game_type")
    .filter(F.col("game_type").isin(game_types))
    .dropDuplicates(["game_id"])
)

season_frames = []
for season in seasons:
    source_path = pbp_parquet_path(pbp_volume, season)
    pbp_df = read_volume_parquet(spark, source_path)
    if "season_type" in pbp_df.columns:
        pbp_df = pbp_df.filter(F.col("season_type") != "PRE")

    pbp_df = pbp_df.join(schedule_df, on="game_id", how="inner")
    if "season" not in pbp_df.columns:
        pbp_df = pbp_df.withColumn("season", F.lit(season))
    pbp_df = (
        pbp_df.withColumn("ingested_at", F.lit(ingested_at))
        .withColumn("_source_file", F.lit(source_path))
    )

    row_count = pbp_df.count()
    print(f"Season {season}: {row_count:,} plays after schedule join")
    season_frames.append(pbp_df)

if not season_frames:
    raise RuntimeError("No PBP seasons loaded")

combined_pbp = union_by_name_harmonized(season_frames).dropDuplicates(["game_id", "play_id"])

(
    combined_pbp.write.format("delta")
    .mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(pbp_table)
)

# COMMAND ----------

display(
    spark.table(pbp_table)
    .groupBy("season", "game_type")
    .count()
    .orderBy("season", "game_type")
)