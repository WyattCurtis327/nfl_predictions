# Databricks notebook source
# MAGIC %md
# MAGIC # Download PBP to UC Volume
# MAGIC Fetches nflverse play-by-play parquet files into `/Volumes/nfl/pbp/raw/`.
# MAGIC Preseason is never included in downloaded files.

# COMMAND ----------

from nfl_predictions.uc_paths import DEFAULT_CATALOG, DEFAULT_PBP_SCHEMA, UcPaths

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("pbp_schema", DEFAULT_PBP_SCHEMA, "PBP schema")
dbutils.widgets.text("pbp_seasons", "2024,2025", "Comma-separated seasons")
dbutils.widgets.text("pbp_volume", "", "UC Volume path")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    pbp=dbutils.widgets.get("pbp_schema"),
)
pbp_seasons_raw = dbutils.widgets.get("pbp_seasons")
pbp_volume = dbutils.widgets.get("pbp_volume").strip() or paths.pbp_volume()

# COMMAND ----------

from nfl_predictions.nflverse_data import NFLVERSE_PBP_URL, PbpNotAvailableError, parse_season_list
from nfl_predictions.pbp_volume import download_pbp_season_to_volume, pbp_parquet_path

seasons = parse_season_list(pbp_seasons_raw)
if not seasons:
    raise ValueError("pbp_seasons must list at least one season")

results: list[dict] = []
for season in seasons:
    try:
        dest = download_pbp_season_to_volume(season, pbp_volume)
        row_count = spark.read.parquet(dest).count()
        results.append(
            {
                "season": season,
                "path": dest,
                "source": NFLVERSE_PBP_URL.format(season=season),
                "rows": row_count,
            }
        )
        print(f"Season {season}: wrote {row_count:,} rows to {dest}")
    except PbpNotAvailableError as exc:
        raise RuntimeError(f"PBP not available for season {season}") from exc

dbutils.jobs.taskValues.set(key="downloaded_seasons", value=",".join(str(s) for s in seasons))
dbutils.jobs.taskValues.set(key="volume_paths", value=",".join(r["path"] for r in results))