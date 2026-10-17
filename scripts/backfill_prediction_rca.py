"""Backfill prediction_rca for historical missed grades via Databricks Connect."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from test_databricks_connect import _load_project_env, _profile

_load_project_env()
profile = _profile()
if not profile:
    raise SystemExit("Set DATABRICKS_CONFIG_PROFILE in .env")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=None, help="Limit to one season")
    parser.add_argument("--dry-run", action="store_true", help="Analyze without writing")
    args = parser.parse_args()

    import pandas as pd
    from databricks.connect import DatabricksSession

    from nfl_predictions.nfelo import nfelo_ratings_lookup, select_nfelo_ratings
    from nfl_predictions.prediction_rca import new_rca_run_id, prepare_rca_log
    from nfl_predictions.rca_tools import filter_unanalyzed_misses, run_rca_batch
    from nfl_predictions.spark_io import append_delta_table
    from nfl_predictions.uc_paths import UcPaths

    spark = DatabricksSession.builder.profile(profile).getOrCreate()
    paths = UcPaths()

    grades_table = paths.prediction_grades_table()
    rca_table = paths.prediction_rca_table()
    pbp_table = paths.pbp_table()

    if not spark.catalog.tableExists(grades_table):
        raise SystemExit(f"Missing {grades_table}")

    grades = spark.table(grades_table).toPandas()
    if args.season is not None:
        grades = grades[grades["season"] == args.season].copy()

    existing_rca = (
        spark.table(rca_table).toPandas()
        if spark.catalog.tableExists(rca_table)
        else pd.DataFrame()
    )
    pending = filter_unanalyzed_misses(grades, existing_rca)
    if pending.empty:
        print("No unanalyzed missed grades found.")
        return

    pbp = spark.table(pbp_table).toPandas() if spark.catalog.tableExists(pbp_table) else pd.DataFrame()
    game_ids = set(pending["game_id"].dropna().astype(str))
    game_pbp_by_id: dict[str, object] = {}
    if not pbp.empty and "game_id" in pbp.columns:
        game_rows = pbp[pbp["game_id"].astype(str).isin(game_ids)]
        for game_id, frame in game_rows.groupby("game_id"):
            game_pbp_by_id[str(game_id)] = frame.reset_index(drop=True)

    nfelo_games = pd.DataFrame()
    nfelo_lookup: dict[str, float] = {}
    ratings_table = paths.nfelo_ratings_table()
    games_table = paths.nfelo_games_table()
    if spark.catalog.tableExists(ratings_table) and not pending.empty:
        season = int(pending["season"].iloc[0])
        week = int(pending["week"].iloc[0])
        nfelo_lookup = nfelo_ratings_lookup(
            select_nfelo_ratings(spark.table(ratings_table).toPandas(), season=season, week=week)
        )
    if spark.catalog.tableExists(games_table):
        nfelo_games = spark.table(games_table).toPandas()

    reports = run_rca_batch(
        pending,
        pbp=pbp,
        game_pbp_by_id=game_pbp_by_id,
        nfelo_games=nfelo_games,
        nfelo_lookup=nfelo_lookup,
    )
    if reports.empty:
        print("RCA produced no rows.")
        return

    rca_run_id = new_rca_run_id()
    logged = prepare_rca_log(reports, rca_run_id=rca_run_id, grading_run_id=None)
    print(f"Prepared {len(logged)} RCA rows (rca_run_id={rca_run_id})")
    if args.dry_run:
        print(logged[["game_id", "miss_types", "primary_cause"]].to_string(index=False))
        return

    append_delta_table(spark, logged, rca_table)
    print(f"Appended {len(logged)} rows to {rca_table}")


if __name__ == "__main__":
    main()