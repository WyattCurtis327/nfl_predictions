# Databricks notebook source
# MAGIC %md
# MAGIC # Validate weekly refresh
# MAGIC Terminal gate for `nfl_weekly_refresh`. Confirms schedules, rosters, players,
# MAGIC PBP, and live odds are ready for predictions.

# COMMAND ----------

from nfl_predictions.uc_paths import (
    DEFAULT_CATALOG,
    DEFAULT_ODDS_SCHEMA,
    DEFAULT_PBP_SCHEMA,
    DEFAULT_PLAYERS_SCHEMA,
    DEFAULT_ROSTERS_SCHEMA,
    DEFAULT_SCHEDULES_SCHEMA,
    UcPaths,
)

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("schedules_schema", DEFAULT_SCHEDULES_SCHEMA, "Schedules schema")
dbutils.widgets.text("pbp_schema", DEFAULT_PBP_SCHEMA, "PBP schema")
dbutils.widgets.text("rosters_schema", DEFAULT_ROSTERS_SCHEMA, "Rosters schema")
dbutils.widgets.text("players_schema", DEFAULT_PLAYERS_SCHEMA, "Players schema")
dbutils.widgets.text("odds_schema", DEFAULT_ODDS_SCHEMA, "Odds schema")
dbutils.widgets.text("schedule_season", "2026", "Active schedule season")
dbutils.widgets.text("current_pbp_season", "2026", "Current PBP season")
dbutils.widgets.text("preferred_bookmaker", "draftkings", "Preferred bookmaker")
dbutils.widgets.text("min_match_rate", "0.9", "Minimum live-odds match rate")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    schedules=dbutils.widgets.get("schedules_schema"),
    pbp=dbutils.widgets.get("pbp_schema"),
    rosters=dbutils.widgets.get("rosters_schema"),
    players=dbutils.widgets.get("players_schema"),
    odds=dbutils.widgets.get("odds_schema"),
)
season = int(dbutils.widgets.get("schedule_season"))
current_pbp_season = int(dbutils.widgets.get("current_pbp_season"))
preferred_bookmaker = dbutils.widgets.get("preferred_bookmaker").strip()
min_match_rate = float(dbutils.widgets.get("min_match_rate"))

games_table = paths.schedules_games_table()
pbp_table = paths.pbp_table()
rosters_table = paths.rosters_table()
players_table = paths.players_table()
latest_table = paths.game_odds_latest_table()

# COMMAND ----------

from nfl_predictions.validate import (
    WeeklyRefreshValidationError,
    build_weekly_refresh_checks,
    failed_blocking_checks,
)

required_tables = {
    "games": games_table,
    "play_by_play": pbp_table,
    "rosters": rosters_table,
    "players": players_table,
    "game_odds_latest": latest_table,
}
missing = [name for name, table in required_tables.items() if not spark.catalog.tableExists(table)]
if missing:
    raise WeeklyRefreshValidationError(
        "Weekly refresh validation failed: missing tables: " + ", ".join(missing)
    )

schedule_pdf = spark.table(games_table).dropDuplicates(["game_id"]).toPandas()
odds_pdf = spark.table(latest_table).toPandas()
pbp_rows = int(
    spark.table(pbp_table).filter(f"season = {current_pbp_season}").count()
)
roster_rows = int(spark.table(rosters_table).count())
player_rows = int(spark.table(players_table).count())

checks = build_weekly_refresh_checks(
    schedule=schedule_pdf,
    game_odds_latest=odds_pdf,
    season=season,
    pbp_rows=pbp_rows,
    roster_rows=roster_rows,
    player_rows=player_rows,
    min_match_rate=min_match_rate,
    preferred_bookmaker=preferred_bookmaker,
)

# COMMAND ----------

import pandas as pd

summary = pd.DataFrame(checks)
display(summary)

failed = failed_blocking_checks(checks)
if failed:
    raise WeeklyRefreshValidationError(
        "Weekly refresh validation failed: " + ", ".join(failed)
    )

print("Weekly refresh validation passed.")