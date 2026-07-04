# Databricks notebook source
# MAGIC %md
# MAGIC # Validate bootstrap
# MAGIC Terminal gate for `nfl_bootstrap`. Fails the job when required checks do not pass.

# COMMAND ----------

from nfl_predictions.uc_paths import (
    DEFAULT_CATALOG,
    DEFAULT_ODDS_SCHEMA,
    DEFAULT_PBP_SCHEMA,
    DEFAULT_PLAYERS_SCHEMA,
    DEFAULT_ROSTERS_SCHEMA,
    DEFAULT_SCHEDULES_SCHEMA,
    DEFAULT_TEAMS_SCHEMA,
    UcPaths,
)

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("teams_schema", DEFAULT_TEAMS_SCHEMA, "Teams schema")
dbutils.widgets.text("schedules_schema", DEFAULT_SCHEDULES_SCHEMA, "Schedules schema")
dbutils.widgets.text("pbp_schema", DEFAULT_PBP_SCHEMA, "PBP schema")
dbutils.widgets.text("rosters_schema", DEFAULT_ROSTERS_SCHEMA, "Rosters schema")
dbutils.widgets.text("players_schema", DEFAULT_PLAYERS_SCHEMA, "Players schema")
dbutils.widgets.text("odds_schema", DEFAULT_ODDS_SCHEMA, "Odds schema")
dbutils.widgets.text("min_reg_games", "272", "Minimum REG games per backfill season")
dbutils.widgets.text("min_match_rate", "0.9", "Minimum odds match rate for backfill seasons")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    teams=dbutils.widgets.get("teams_schema"),
    schedules=dbutils.widgets.get("schedules_schema"),
    pbp=dbutils.widgets.get("pbp_schema"),
    rosters=dbutils.widgets.get("rosters_schema"),
    players=dbutils.widgets.get("players_schema"),
    odds=dbutils.widgets.get("odds_schema"),
)
min_reg_games = int(dbutils.widgets.get("min_reg_games"))
min_match_rate = float(dbutils.widgets.get("min_match_rate"))

teams_table = paths.teams_table()
games_table = paths.schedules_games_table()
pbp_table = paths.pbp_table()
players_table = paths.players_table()

# COMMAND ----------

from typing import Any


class BootstrapValidationError(RuntimeError):
    """Raised when one or more bootstrap checks fail."""


def table_exists(name: str) -> bool:
    return spark.catalog.tableExists(name)


def count_sql(table: str, where: str = "1=1") -> int:
    return int(spark.sql(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}").collect()[0]["n"])


def count_duplicate_keys(table: str, keys: list[str]) -> int:
    key_list = ", ".join(keys)
    return int(
        spark.sql(
            f"""
            SELECT COUNT(*) AS n FROM (
              SELECT {key_list} FROM {table}
              GROUP BY {key_list} HAVING COUNT(*) > 1
            )
            """
        ).collect()[0]["n"]
    )


checks: list[dict[str, Any]] = []

# Teams — nflverse teams.csv is historical; validate the latest season only
if table_exists(teams_table):
    latest_season = int(
        spark.sql(f"SELECT MAX(season) AS season FROM {teams_table}").collect()[0]["season"]
    )
    team_count = count_sql(teams_table, f"season = {latest_season}")
    checks.append(
        {
            "name": "teams_count",
            "expect": f"32 teams in season {latest_season}",
            "actual": team_count,
            "passed": team_count == 32,
            "blocking": True,
        }
    )
else:
    checks.append(
        {
            "name": "teams_count",
            "expect": "32 teams",
            "actual": "table missing",
            "passed": False,
            "blocking": True,
        }
    )

# Schedules — REG game counts for backfill seasons
if table_exists(games_table):
    pre_count = count_sql(games_table, "game_type = 'PRE'")
    checks.append(
        {
            "name": "schedule_no_preseason",
            "expect": "0 PRE games",
            "actual": pre_count,
            "passed": pre_count == 0,
            "blocking": True,
        }
    )
    dup_games = count_duplicate_keys(games_table, ["game_id"])
    checks.append(
        {
            "name": "schedule_no_duplicate_game_ids",
            "expect": "0 duplicate game_id",
            "actual": dup_games,
            "passed": dup_games == 0,
            "blocking": True,
        }
    )
    for season in (2024, 2025):
        reg_count = count_sql(games_table, f"season = {season} AND game_type = 'REG'")
        checks.append(
            {
                "name": f"schedule_{season}_reg_games",
                "expect": f">= {min_reg_games} REG games",
                "actual": reg_count,
                "passed": reg_count >= min_reg_games,
                "blocking": True,
            }
        )
else:
    for season in (2024, 2025):
        checks.append(
            {
                "name": f"schedule_{season}_reg_games",
                "expect": f">= {min_reg_games} REG games",
                "actual": "table missing",
                "passed": False,
                "blocking": True,
            }
        )

# PBP — required for full bootstrap
if table_exists(pbp_table):
    pre_pbp = count_sql(pbp_table, "season_type = 'PRE'")
    pbp_rows = count_sql(pbp_table)
    checks.append(
        {
            "name": "pbp_no_preseason",
            "expect": "0 PRE rows in PBP",
            "actual": pre_pbp,
            "passed": pre_pbp == 0,
            "blocking": True,
        }
    )
    checks.append(
        {
            "name": "pbp_has_rows",
            "expect": "> 0 play rows",
            "actual": pbp_rows,
            "passed": pbp_rows > 0,
            "blocking": True,
        }
    )
    for season in (2024, 2025):
        season_rows = count_sql(pbp_table, f"season = {season}")
        checks.append(
            {
                "name": f"pbp_{season}_rows",
                "expect": f"> 0 plays for season {season}",
                "actual": season_rows,
                "passed": season_rows > 0,
                "blocking": True,
            }
        )
else:
    checks.append(
        {
            "name": "pbp_table_exists",
            "expect": "play_by_play table present",
            "actual": "missing",
            "passed": False,
            "blocking": True,
        }
    )

# Players — no duplicate player_id when table exists
if table_exists(players_table):
    dup_players = spark.sql(
        f"""
        SELECT COUNT(*) AS n FROM (
          SELECT player_id FROM {players_table}
          GROUP BY player_id HAVING COUNT(*) > 1
        )
        """
    ).collect()[0]["n"]
    checks.append(
        {
            "name": "players_no_duplicate_ids",
            "expect": "0 duplicate player_id",
            "actual": int(dup_players),
            "passed": int(dup_players) == 0,
            "blocking": True,
        }
    )
else:
    checks.append(
        {
            "name": "players_no_duplicate_ids",
            "expect": "0 duplicate player_id",
            "actual": "table missing",
            "passed": False,
            "blocking": True,
        }
    )

# Odds — nflverse closing lines extracted from schedules
game_odds_table = paths.game_odds_table()
gaps_table = paths.odds_ingest_gaps_table()
odds_tables = {
    "game_odds": game_odds_table,
    "odds_lines": paths.odds_lines_table(),
    "game_odds_latest": paths.game_odds_latest_table(),
}

if all(table_exists(name) for name in odds_tables.values()):
    odds_rows = count_sql(game_odds_table)
    checks.append(
        {
            "name": "odds_has_rows",
            "expect": "> 0 game odds rows",
            "actual": odds_rows,
            "passed": odds_rows > 0,
            "blocking": True,
        }
    )
    dup_game_odds = count_duplicate_keys(game_odds_table, ["game_id"])
    checks.append(
        {
            "name": "odds_no_duplicate_game_ids",
            "expect": "0 duplicate game_id in game_odds",
            "actual": dup_game_odds,
            "passed": dup_game_odds == 0,
            "blocking": True,
        }
    )
    dup_odds_lines = count_duplicate_keys(
        odds_tables["odds_lines"],
        ["game_id", "market", "side"],
    )
    checks.append(
        {
            "name": "odds_lines_no_duplicate_keys",
            "expect": "0 duplicate game_id/market/side",
            "actual": dup_odds_lines,
            "passed": dup_odds_lines == 0,
            "blocking": True,
        }
    )
    for season in (2024, 2025):
        scheduled = count_sql(
            games_table,
            f"season = {season} AND game_type IN ('REG','WC','DIV','CON','SB')",
        )
        matched = int(
            spark.sql(
                f"""
                SELECT COUNT(DISTINCT game_id) AS n
                FROM {game_odds_table}
                WHERE season = {season}
                  AND spread_line IS NOT NULL
                  AND total_line IS NOT NULL
                  AND away_moneyline IS NOT NULL
                  AND home_moneyline IS NOT NULL
                """
            ).collect()[0]["n"]
        )
        rate = (matched / scheduled) if scheduled else 0.0
        checks.append(
            {
                "name": f"odds_{season}_match_rate",
                "expect": f">= {min_match_rate:.0%} games with nflverse odds",
                "actual": round(rate, 4),
                "passed": rate >= min_match_rate,
                "blocking": True,
            }
        )
else:
    missing = [name for name, table in odds_tables.items() if not table_exists(table)]
    checks.append(
        {
            "name": "odds_tables_exist",
            "expect": "game_odds, odds_lines, game_odds_latest present",
            "actual": f"missing: {', '.join(missing)}",
            "passed": False,
            "blocking": True,
        }
    )

if table_exists(gaps_table):
    gap_count = count_sql(gaps_table)
    checks.append(
        {
            "name": "odds_ingest_gaps",
            "expect": "review gaps manually",
            "actual": gap_count,
            "passed": True,
            "blocking": False,
        }
    )

# COMMAND ----------

import pandas as pd

summary = pd.DataFrame(checks)
display(summary)

failed = [
    row["name"]
    for row in checks
    if row.get("blocking") and not row.get("passed")
]

if failed:
    raise BootstrapValidationError(
        "Bootstrap validation failed: " + ", ".join(failed)
    )

print("Bootstrap validation passed.")