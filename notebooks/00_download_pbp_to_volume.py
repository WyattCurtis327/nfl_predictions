# Databricks notebook source
# MAGIC %md
# MAGIC # Download PBP to UC Volume
# MAGIC Fetches nflverse play-by-play parquet files into `/Volumes/nfl/landing/raw/`.
# MAGIC Preseason is never included in downloaded files.

# COMMAND ----------

from nfl_predictions.uc_paths import DEFAULT_CATALOG, DEFAULT_PBP_SCHEMA, UcPaths

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("pbp_schema", DEFAULT_PBP_SCHEMA, "PBP schema")
dbutils.widgets.text("pbp_seasons", "2024,2025", "Comma-separated seasons")
dbutils.widgets.text("pbp_volume", "", "UC Volume path")
dbutils.widgets.dropdown(
    "skip_unavailable_seasons",
    "false",
    ["true", "false"],
    "Skip seasons nflverse has not published yet",
)

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    pbp=dbutils.widgets.get("pbp_schema"),
)
pbp_seasons_raw = dbutils.widgets.get("pbp_seasons")
pbp_volume = dbutils.widgets.get("pbp_volume").strip() or paths.pbp_volume()

# COMMAND ----------

from nfl_predictions.nflverse_data import parse_season_list
from nfl_predictions.pbp_volume import download_pbp_seasons_to_volume

seasons = parse_season_list(pbp_seasons_raw)
if not seasons:
    raise ValueError("pbp_seasons must list at least one season")

skip_unavailable = dbutils.widgets.get("skip_unavailable_seasons").lower() == "true"
downloads, skipped = download_pbp_seasons_to_volume(
    seasons,
    pbp_volume,
    skip_unavailable=skip_unavailable,
)

results: list[dict] = []
for entry in downloads:
    season = int(entry["season"])
    dest = str(entry["path"])
    row_count = spark.read.parquet(dest).count()
    results.append({**entry, "rows": row_count})
    print(f"Season {season}: wrote {row_count:,} rows to {dest}")

for season in skipped:
    print(f"Season {season}: skipped (nflverse PBP not published yet)")

if not results and not skip_unavailable:
    raise RuntimeError(f"PBP not available for seasons: {seasons}")

downloaded_seasons = [str(entry["season"]) for entry in results]
dbutils.jobs.taskValues.set(key="downloaded_seasons", value=",".join(downloaded_seasons))
dbutils.jobs.taskValues.set(key="skipped_seasons", value=",".join(str(s) for s in skipped))
dbutils.jobs.taskValues.set(key="volume_paths", value=",".join(str(r["path"]) for r in results))