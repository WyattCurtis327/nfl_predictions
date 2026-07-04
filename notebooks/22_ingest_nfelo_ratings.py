# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest nfelo power ratings
# MAGIC Loads the latest team ratings from the public nfelo GitHub repo into
# MAGIC `nfl.teams.nfelo_ratings`. Optionally refreshes per-game nfelo lines in
# MAGIC `nfl.teams.nfelo_games` for the active schedule season.

# COMMAND ----------

from nfl_predictions.uc_paths import DEFAULT_CATALOG, DEFAULT_TEAMS_SCHEMA, UcPaths

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("teams_schema", DEFAULT_TEAMS_SCHEMA, "Teams schema")
dbutils.widgets.text("schedule_season", "2026", "Schedule season for nfelo_games filter")
dbutils.widgets.dropdown("fetch_games", "true", ["true", "false"], "Refresh nfelo_games")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    teams=dbutils.widgets.get("teams_schema"),
)
schedule_season = int(dbutils.widgets.get("schedule_season"))
fetch_games = dbutils.widgets.get("fetch_games").lower() == "true"
ratings_table = paths.nfelo_ratings_table()
games_table = paths.nfelo_games_table()

print(f"Ratings table: {ratings_table}")
print(f"Games table:   {games_table}")

# COMMAND ----------

from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.nfelo import NFELO_SOURCE, fetch_nfelo_games, fetch_nfelo_snapshot
from nfl_predictions.spark_io import write_delta_table

ratings_pdf = fetch_nfelo_snapshot()
ratings_pdf = stamp_dataframe(ratings_pdf, source_file=NFELO_SOURCE)
write_delta_table(spark, ratings_pdf, ratings_table, dedupe_keys=["season", "week", "team"])

print(f"Wrote {len(ratings_pdf)} rows to {ratings_table}")

# COMMAND ----------

if fetch_games:
    games_pdf = fetch_nfelo_games()
    if "game_id" in games_pdf.columns:
        games_pdf["season"] = (
            games_pdf["game_id"].astype(str).str.extract(r"^(\d{4})_")[0].astype("Int64")
        )
        games_pdf = games_pdf[games_pdf["season"] == schedule_season].copy()
    if games_pdf.empty:
        print(f"No nfelo_games rows for season {schedule_season}; skipped {games_table}")
    else:
        games_pdf = stamp_dataframe(games_pdf, source_file=NFELO_SOURCE)
        write_delta_table(spark, games_pdf, games_table, dedupe_keys=["game_id"])
        print(f"Wrote {len(games_pdf)} rows to {games_table}")
else:
    print("fetch_games=false; skipped nfelo_games refresh")