# Databricks notebook source
# MAGIC %md
# MAGIC # Ingest Odds API lines
# MAGIC Fetches live NFL odds (or reads staged JSON), matches `game_id` from
# MAGIC `nfl.landing.games`, and merges into `nfl.landing` odds tables.

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
dbutils.widgets.text("season", "2026", "NFL season")
dbutils.widgets.text("target_week", "", "Week to ingest (blank = all upcoming)")
dbutils.widgets.text("secret_scope", "nfl", "Secret scope")
dbutils.widgets.text("secret_key", "odds_api_key", "Secret key")
dbutils.widgets.text(
    "odds_staging_path",
    "../staging/odds_latest.json",
    "Staged odds JSON when API is unavailable",
)
dbutils.widgets.text("preferred_bookmaker", "draftkings", "Preferred bookmaker key")
dbutils.widgets.text("min_match_rate", "0.9", "Minimum scheduled-game match rate")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    odds=dbutils.widgets.get("odds_schema"),
    schedules=dbutils.widgets.get("schedules_schema"),
)
season = int(dbutils.widgets.get("season"))
target_week_raw = dbutils.widgets.get("target_week").strip()
target_week = int(target_week_raw) if target_week_raw else None
secret_scope = dbutils.widgets.get("secret_scope")
secret_key = dbutils.widgets.get("secret_key")
odds_staging_path = dbutils.widgets.get("odds_staging_path").strip()
preferred_bookmaker = dbutils.widgets.get("preferred_bookmaker").strip()
min_match_rate = float(dbutils.widgets.get("min_match_rate"))

games_table = paths.schedules_games_table()
game_odds_table = paths.game_odds_table()
odds_lines_table = paths.odds_lines_table()
latest_table = paths.game_odds_latest_table()
gaps_table = paths.odds_ingest_gaps_table()

# COMMAND ----------

import json
import os
from datetime import datetime, timezone

from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.odds import (
    GAME_ODDS_KEY,
    ODDS_GAPS_KEY,
    ODDS_LINES_KEY,
    merge_odds_updates,
)
from nfl_predictions.odds_api import (
    OddsApiError,
    assess_schedule_match_rate,
    build_odds_from_api,
    fetch_nfl_odds,
)
from nfl_predictions.simulation import filter_schedule_game_types, infer_next_week
from nfl_predictions.spark_io import write_delta_table


def _resolve_staging_path(path: str) -> str:
    if not path:
        return ""
    if os.path.isabs(path) and os.path.isfile(path):
        return path
    candidates = [
        os.path.abspath(os.path.join(os.getcwd(), path)),
        os.path.abspath(os.path.join(os.getcwd(), "..", path)),
        os.path.abspath(os.path.join(os.getcwd(), "..", "files", path.lstrip("./"))),
    ]
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return ""


def _load_staged_odds(path: str) -> tuple[list, dict]:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload["games"], payload.get("headers", {})


def _read_table_pdf(table: str):
    if spark.catalog.tableExists(table):
        return spark.table(table).toPandas()
    return None


if not spark.catalog.tableExists(games_table):
    raise ValueError(f"Schedule table {games_table} must exist before ingesting odds")

schedule_pdf = spark.table(games_table).dropDuplicates(["game_id"]).toPandas()
season_schedule = filter_schedule_game_types(schedule_pdf)
season_schedule = season_schedule[season_schedule["season"] == season].copy()

if target_week is None:
    target_week = infer_next_week(season_schedule, season=season)
    if target_week is None:
        raise ValueError("No unplayed REG/playoff weeks found; set target_week explicitly.")

schedule_subset = season_schedule[season_schedule["week"] == target_week].copy()
print(f"Ingesting Odds API lines for season {season} week {target_week}")

ingested_at = datetime.now(timezone.utc)
staging_file = _resolve_staging_path(odds_staging_path)

if staging_file:
    odds_games, headers = _load_staged_odds(staging_file)
    source_file = f"odds_api:staged:{staging_file}"
    source_label = f"staged file: {staging_file}"
else:
    api_key = dbutils.secrets.get(scope=secret_scope, key=secret_key).strip()
    try:
        odds_games, headers = fetch_nfl_odds(api_key)
        source_file = "odds_api:live"
        source_label = "odds api"
    except (OddsApiError, ConnectionError) as exc:
        raise RuntimeError(
            "Odds API unavailable from serverless and no staged odds file found. "
            "Run scripts/stage_odds.py locally, deploy, then rerun."
        ) from exc

print(
    "Loaded",
    len(odds_games),
    "games from",
    source_label + ";",
    "requests remaining:",
    headers.get("x-requests-remaining"),
)

# COMMAND ----------

game_odds_df, odds_lines_df, latest_df, gaps_df = build_odds_from_api(
    odds_games,
    schedule_pdf,
    season=season,
    week=target_week,
    preferred_bookmaker=preferred_bookmaker,
    ingested_at=ingested_at,
)

match_stats = assess_schedule_match_rate(
    schedule_subset,
    game_odds_df,
    min_rate=min_match_rate,
)
print(
    "scheduled game_id match rate:",
    f"{match_stats['matched_games']}/{match_stats['total_games']}",
    f"({match_stats['match_rate']:.1%})",
)

if not match_stats["passed"]:
    preview = gaps_df.head(5).to_dict(orient="records") if not gaps_df.empty else []
    raise RuntimeError(
        f"game_id match rate {match_stats['match_rate']:.1%} below minimum "
        f"{min_match_rate:.1%}. Sample unmatched games: {preview}"
    )

game_odds_pdf = stamp_dataframe(game_odds_df, source_file=source_file, ingested_at=ingested_at)
odds_lines_pdf = stamp_dataframe(odds_lines_df, source_file=source_file, ingested_at=ingested_at)
latest_pdf = stamp_dataframe(latest_df, source_file=source_file, ingested_at=ingested_at)
gaps_pdf = stamp_dataframe(gaps_df, source_file=source_file, ingested_at=ingested_at)

existing_game_odds = _read_table_pdf(game_odds_table)
existing_odds_lines = _read_table_pdf(odds_lines_table)
existing_latest = _read_table_pdf(latest_table)
existing_gaps = _read_table_pdf(gaps_table)

merged_game_odds = merge_odds_updates(existing_game_odds, game_odds_pdf, dedupe_keys=GAME_ODDS_KEY)
merged_odds_lines = merge_odds_updates(existing_odds_lines, odds_lines_pdf, dedupe_keys=ODDS_LINES_KEY)
merged_latest = merge_odds_updates(existing_latest, latest_pdf, dedupe_keys=GAME_ODDS_KEY)
merged_gaps = merge_odds_updates(existing_gaps, gaps_pdf, dedupe_keys=ODDS_GAPS_KEY)

print(f"incoming game_odds: {len(game_odds_pdf):,}")
print(f"merged game_odds: {len(merged_game_odds):,}")
print(f"merged game_odds_latest: {len(merged_latest):,}")
print(f"merged odds_ingest_gaps: {len(merged_gaps):,}")

# COMMAND ----------

table_specs = [
    (merged_game_odds, game_odds_table, GAME_ODDS_KEY),
    (merged_odds_lines, odds_lines_table, ODDS_LINES_KEY),
    (merged_latest, latest_table, GAME_ODDS_KEY),
    (merged_gaps, gaps_table, ODDS_GAPS_KEY),
]
for pdf, table, dedupe_keys in table_specs:
    write_delta_table(spark, pdf, table, dedupe_keys=dedupe_keys)

latest_view = spark.table(latest_table).filter(f"season = {season}")
if target_week is not None:
    latest_view = latest_view.filter(f"week = {target_week}")
display(latest_view.orderBy("gameday", "game_id"))