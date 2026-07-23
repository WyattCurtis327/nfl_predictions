"""Backfill prediction_grades (and optional RCA) for existing gold predictions.

Uses Databricks Connect. Grades every completed season/week that has predictions
and final scores, writing into the medallion gold schema via UcPaths defaults.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from test_databricks_connect import _load_project_env, _profile

_load_project_env()
profile = _profile()
if not profile:
    raise SystemExit("Set DATABRICKS_CONFIG_PROFILE in .env")


def _grade_week(
    *,
    spark,
    paths,
    schedule_pdf: pd.DataFrame,
    predictions_pdf: pd.DataFrame,
    existing_grades: pd.DataFrame,
    season: int,
    week: int,
    model_id: str | None,
    dry_run: bool,
    log_rca: bool,
) -> tuple[int, int, pd.DataFrame]:
    from nfl_predictions.simulation import (
        filter_ungraded_predictions,
        grade_predictions,
        new_grading_run_id,
        select_latest_prediction_run,
        select_latest_predictions_per_game,
        summarize_prediction_accuracy,
    )
    from nfl_predictions.spark_io import append_delta_table

    week_predictions = predictions_pdf[
        (predictions_pdf["season"] == season) & (predictions_pdf["week"] == week)
    ].copy()
    if week_predictions.empty:
        return 0, 0, existing_grades

    if model_id:
        week_predictions = week_predictions[
            week_predictions["model_id"].fillna("monte_carlo") == model_id
        ].copy()
        if week_predictions.empty:
            return 0, 0, existing_grades

    latest_run_id = select_latest_prediction_run(
        week_predictions,
        season=season,
        week=week,
        model_id=model_id,
    )
    if latest_run_id:
        week_predictions = week_predictions[
            week_predictions["prediction_run_id"] == latest_run_id
        ].copy()

    week_predictions = select_latest_predictions_per_game(
        week_predictions,
        model_id=model_id,
    )
    pending = filter_ungraded_predictions(week_predictions, existing_grades)
    if pending.empty:
        return 0, 0, existing_grades

    schedule_season = schedule_pdf[schedule_pdf["season"] == season].copy()
    graded = grade_predictions(pending, schedule_season)
    if graded.empty:
        return 0, 0, existing_grades

    grading_run_id = new_grading_run_id()
    graded["grading_run_id"] = grading_run_id
    metrics = summarize_prediction_accuracy(graded)
    spread_acc = metrics.get("spread_accuracy")
    total_acc = metrics.get("total_accuracy")
    spread_txt = f"{spread_acc * 100:.1f}%" if spread_acc is not None else "n/a"
    total_txt = f"{total_acc * 100:.1f}%" if total_acc is not None else "n/a"
    print(
        f"  season={season} week={week}: {len(graded)} grades "
        f"(spread {spread_txt}, total {total_txt})"
    )

    if dry_run:
        return len(graded), 0, existing_grades

    append_delta_table(spark, graded, paths.prediction_grades_table())
    existing_grades = pd.concat([existing_grades, graded], ignore_index=True)

    rca_rows = 0
    if log_rca:
        from nfl_predictions.nfelo import nfelo_ratings_lookup, select_nfelo_ratings
        from nfl_predictions.prediction_rca import (
            analyze_missed_grades,
            filter_missed_grades,
            new_rca_run_id,
            prepare_rca_log,
        )

        missed = filter_missed_grades(graded)
        if not missed.empty:
            pbp_table = paths.pbp_table()
            pbp_pdf = (
                spark.table(pbp_table).toPandas()
                if spark.catalog.tableExists(pbp_table)
                else pd.DataFrame()
            )
            game_ids = set(missed["game_id"].dropna().astype(str))
            game_pbp_by_id: dict[str, pd.DataFrame] = {}
            if not pbp_pdf.empty and "game_id" in pbp_pdf.columns:
                game_rows = pbp_pdf[pbp_pdf["game_id"].astype(str).isin(game_ids)]
                for game_id, frame in game_rows.groupby("game_id"):
                    game_pbp_by_id[str(game_id)] = frame.reset_index(drop=True)

            nfelo_lookup: dict[str, float] = {}
            nfelo_games = pd.DataFrame()
            ratings_table = paths.nfelo_ratings_table()
            games_table = paths.nfelo_games_table()
            if spark.catalog.tableExists(ratings_table):
                nfelo_lookup = nfelo_ratings_lookup(
                    select_nfelo_ratings(
                        spark.table(ratings_table).toPandas(),
                        season=season,
                        week=week,
                    )
                )
            if spark.catalog.tableExists(games_table):
                nfelo_games = spark.table(games_table).toPandas()

            rca_reports = analyze_missed_grades(
                missed,
                pbp=pbp_pdf,
                game_pbp_by_id=game_pbp_by_id,
                nfelo_games=nfelo_games,
                nfelo_lookup=nfelo_lookup,
                current_pbp_season=season,
            )
            rca_run_id = new_rca_run_id()
            rca_pdf = prepare_rca_log(
                rca_reports,
                rca_run_id=rca_run_id,
                grading_run_id=grading_run_id,
            )
            if not rca_pdf.empty:
                append_delta_table(spark, rca_pdf, paths.prediction_rca_table())
                rca_rows = len(rca_pdf)
                print(f"    RCA: {rca_rows} miss rows")

    return len(graded), rca_rows, existing_grades


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--season", type=int, default=None, help="Limit to one season")
    parser.add_argument(
        "--model-id",
        default="monte_carlo",
        help="Model to grade (blank = all models in latest run selection)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-rca",
        action="store_true",
        help="Only write grades, skip RCA for missed picks",
    )
    args = parser.parse_args()

    from databricks.connect import DatabricksSession

    from nfl_predictions.simulation import (
        filter_schedule_game_types,
        prepare_schedule_for_grading,
    )
    from nfl_predictions.uc_paths import UcPaths

    spark = DatabricksSession.builder.profile(profile).getOrCreate()
    paths = UcPaths()
    model_id = args.model_id.strip() or None

    preds_table = paths.game_predictions_table()
    grades_table = paths.prediction_grades_table()
    schedule_table = paths.schedules_games_table()

    print(f"Predictions: {preds_table}")
    print(f"Grades:      {grades_table}")
    print(f"Schedule:    {schedule_table}")
    print(f"RCA:         {paths.prediction_rca_table()}")

    if not spark.catalog.tableExists(preds_table):
        raise SystemExit(f"Missing {preds_table}")
    if not spark.catalog.tableExists(schedule_table):
        raise SystemExit(f"Missing {schedule_table}")

    predictions_pdf = spark.table(preds_table).toPandas()
    if predictions_pdf.empty:
        raise SystemExit("No predictions to grade")

    schedule_pdf = filter_schedule_game_types(spark.table(schedule_table).toPandas())
    schedule_pdf = prepare_schedule_for_grading(schedule_pdf)

    existing_grades = (
        spark.table(grades_table).toPandas()
        if spark.catalog.tableExists(grades_table)
        else pd.DataFrame()
    )

    pairs = (
        predictions_pdf[["season", "week"]]
        .dropna()
        .drop_duplicates()
        .sort_values(["season", "week"])
    )
    if args.season is not None:
        pairs = pairs[pairs["season"] == args.season]

    total_grades = 0
    total_rca = 0
    for row in pairs.itertuples(index=False):
        season = int(row.season)
        week = int(row.week)
        g, r, existing_grades = _grade_week(
            spark=spark,
            paths=paths,
            schedule_pdf=schedule_pdf,
            predictions_pdf=predictions_pdf,
            existing_grades=existing_grades,
            season=season,
            week=week,
            model_id=model_id,
            dry_run=args.dry_run,
            log_rca=not args.skip_rca,
        )
        total_grades += g
        total_rca += r

    mode = "dry-run" if args.dry_run else "wrote"
    print(f"Done ({mode}): {total_grades} grades, {total_rca} RCA rows")


if __name__ == "__main__":
    main()
