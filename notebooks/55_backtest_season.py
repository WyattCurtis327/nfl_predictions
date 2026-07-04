# Databricks notebook source
# MAGIC %md
# MAGIC # Backtest season
# MAGIC Replay weekly predictions for a completed REG season using prior-season PBP,
# MAGIC then grade every week against actual outcomes. Appends to
# MAGIC `game_predictions` and `prediction_grades`.

# COMMAND ----------

from nfl_predictions.uc_paths import (
    DEFAULT_CATALOG,
    DEFAULT_ODDS_SCHEMA,
    DEFAULT_PBP_SCHEMA,
    DEFAULT_PREDICTIONS_SCHEMA,
    DEFAULT_SCHEDULES_SCHEMA,
    DEFAULT_TEAMS_SCHEMA,
    UcPaths,
)

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("schedules_schema", DEFAULT_SCHEDULES_SCHEMA, "Schedules schema")
dbutils.widgets.text("pbp_schema", DEFAULT_PBP_SCHEMA, "PBP schema")
dbutils.widgets.text("odds_schema", DEFAULT_ODDS_SCHEMA, "Odds schema")
dbutils.widgets.text("predictions_schema", DEFAULT_PREDICTIONS_SCHEMA, "Predictions schema")
dbutils.widgets.text("teams_schema", DEFAULT_TEAMS_SCHEMA, "Teams schema")
dbutils.widgets.text("season", "2025", "Season to backtest")
dbutils.widgets.text("pbp_season", "2024", "Prior-season PBP for team profiles")
dbutils.widgets.text("current_pbp_season", "2026", "In-season PBP (use empty season to avoid lookahead)")
dbutils.widgets.text("start_week", "1", "First REG week")
dbutils.widgets.text("end_week", "18", "Last REG week")
dbutils.widgets.text("n_simulations", "10000", "Monte Carlo simulations per game")
dbutils.widgets.text("market_blend", "0.35", "Weight given to market lines (0-1)")
dbutils.widgets.text("nfelo_blend", "0.30", "Weight given to nfelo ratings (0-1)")
dbutils.widgets.dropdown("use_nfelo", "true", ["true", "false"], "Blend nfelo power ratings")
dbutils.widgets.text("pick_threshold", "0.55", "Min confidence to highlight a pick")
dbutils.widgets.text("preferred_bookmaker", "nflverse", "Bookmaker for historical odds")
dbutils.widgets.text("mlflow_experiment", "/Shared/nfl_predictions", "MLflow experiment path")
dbutils.widgets.dropdown("log_predictions", "true", ["true", "false"], "Append predictions")
dbutils.widgets.dropdown("log_grades", "true", ["true", "false"], "Append grades")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    schedules=dbutils.widgets.get("schedules_schema"),
    pbp=dbutils.widgets.get("pbp_schema"),
    odds=dbutils.widgets.get("odds_schema"),
    predictions=dbutils.widgets.get("predictions_schema"),
    teams=dbutils.widgets.get("teams_schema"),
)
season = int(dbutils.widgets.get("season"))
pbp_season = int(dbutils.widgets.get("pbp_season"))
current_pbp_season = int(dbutils.widgets.get("current_pbp_season"))
start_week = int(dbutils.widgets.get("start_week"))
end_week = int(dbutils.widgets.get("end_week"))
n_simulations = int(dbutils.widgets.get("n_simulations"))
market_blend = float(dbutils.widgets.get("market_blend"))
nfelo_blend = float(dbutils.widgets.get("nfelo_blend"))
use_nfelo = dbutils.widgets.get("use_nfelo").lower() == "true"
pick_threshold = float(dbutils.widgets.get("pick_threshold"))
preferred_bookmaker = dbutils.widgets.get("preferred_bookmaker").strip()
mlflow_experiment = dbutils.widgets.get("mlflow_experiment").strip()
log_predictions = dbutils.widgets.get("log_predictions").lower() == "true"
log_grades = dbutils.widgets.get("log_grades").lower() == "true"

pbp_table = paths.pbp_table()
odds_table = paths.game_odds_latest_table()
schedule_table = paths.schedules_games_table()
predictions_table = paths.game_predictions_table()
grades_table = paths.prediction_grades_table()

print(f"Backtest season: {season}")
print(f"PBP profiles:    {pbp_season} only (current={current_pbp_season})")
print(f"Weeks:           {start_week}-{end_week}")
print(f"Bookmaker:       {preferred_bookmaker or 'any'}")

# COMMAND ----------

import pandas as pd

from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.nfelo import select_nfelo_ratings
from nfl_predictions.simulation import (
    SimulationConfig,
    combine_pbp_seasons,
    compute_team_scoring_profiles,
    filter_schedule_game_types,
    filter_ungraded_predictions,
    grade_predictions,
    list_reg_weeks_with_odds,
    new_grading_run_id,
    new_prediction_run_id,
    prepare_odds_for_simulation,
    prepare_prediction_log,
    prepare_schedule_for_grading,
    simulate_weekly_picks,
    summarize_prediction_accuracy,
)
from nfl_predictions.spark_io import append_delta_table

pbp_all = spark.table(pbp_table).toPandas()
pbp_pdf = combine_pbp_seasons(
    pbp_all,
    pbp_all,
    prior_season=pbp_season,
    current_season=current_pbp_season,
)
if pbp_pdf.empty:
    raise ValueError(
        f"No PBP rows for seasons {pbp_season}/{current_pbp_season} in {pbp_table}"
    )

odds_pdf = prepare_odds_for_simulation(
    spark.table(odds_table).toPandas(),
    preferred_bookmaker=preferred_bookmaker or None,
)
schedule_pdf = filter_schedule_game_types(spark.table(schedule_table).toPandas())
schedule_pdf = schedule_pdf[schedule_pdf["season"] == season].copy()
schedule_grading = prepare_schedule_for_grading(schedule_pdf)

profiles = compute_team_scoring_profiles(pbp_pdf)
config = SimulationConfig(
    n_simulations=n_simulations,
    market_blend=market_blend,
    nfelo_blend=nfelo_blend if use_nfelo else 0.0,
    pick_threshold=pick_threshold,
)

nfelo_ratings_all = (
    spark.table(paths.nfelo_ratings_table()).toPandas()
    if use_nfelo and spark.catalog.tableExists(paths.nfelo_ratings_table())
    else pd.DataFrame()
)
nfelo_games_all = (
    spark.table(paths.nfelo_games_table()).toPandas()
    if use_nfelo and spark.catalog.tableExists(paths.nfelo_games_table())
    else pd.DataFrame()
)

weeks = list_reg_weeks_with_odds(
    odds_pdf,
    schedule_pdf,
    season=season,
    start_week=start_week,
    end_week=end_week,
)
if not weeks:
    raise ValueError(
        f"No REG weeks with odds found for season {season} in weeks {start_week}-{end_week}"
    )

existing_predictions = (
    spark.table(predictions_table).toPandas()
    if spark.catalog.tableExists(predictions_table)
    else pd.DataFrame()
)
existing_grades = (
    spark.table(grades_table).toPandas()
    if spark.catalog.tableExists(grades_table)
    else pd.DataFrame()
)

print(f"Simulating {len(weeks)} weeks with {len(profiles)} team profiles")

# COMMAND ----------

import mlflow

week_summaries: list[dict] = []
season_graded_frames: list[pd.DataFrame] = []

mlflow.set_experiment(mlflow_experiment)

for week in weeks:
    week_nfelo_ratings = (
        select_nfelo_ratings(nfelo_ratings_all, season=season, week=week)
        if use_nfelo
        else pd.DataFrame()
    )
    week_nfelo_games = (
        nfelo_games_all[nfelo_games_all["game_id"].astype(str).str.contains(f"_{week:02d}_")]
        if use_nfelo and not nfelo_games_all.empty and "game_id" in nfelo_games_all.columns
        else pd.DataFrame()
    )
    picks = simulate_weekly_picks(
        odds_pdf,
        profiles,
        week=week,
        schedule=schedule_pdf,
        config=config,
        include_completed=True,
        nfelo_ratings=week_nfelo_ratings,
        nfelo_games=week_nfelo_games,
    )
    if picks.empty:
        print(f"Week {week}: no odds rows; skipped")
        continue

    prediction_run_id = new_prediction_run_id()
    prediction_log = prepare_prediction_log(
        picks,
        season=season,
        pbp_season=pbp_season,
        prediction_run_id=prediction_run_id,
        config=config,
    )
    prediction_log = stamp_dataframe(
        prediction_log,
        source_file=f"backtest_season:{season}:wk{week}:{prediction_run_id}",
    )

    if log_predictions:
        with mlflow.start_run(run_name=f"backtest_{season}_wk{week}") as run:
            prediction_log["mlflow_run_id"] = run.info.run_id
            mlflow.log_params(
                {
                    "season": season,
                    "week": week,
                    "pbp_season": pbp_season,
                    "current_pbp_season": current_pbp_season,
                    "backtest": True,
                    "prediction_run_id": prediction_run_id,
                }
            )
            mlflow.log_metrics(
                {
                    "games_predicted": float(len(prediction_log)),
                    "avg_spread_confidence": float(
                        prediction_log["spread_confidence"].mean()
                    ),
                    "avg_total_confidence": float(
                        prediction_log["total_confidence"].mean()
                    ),
                }
            )
            append_delta_table(spark, prediction_log, predictions_table)
    else:
        prediction_log["mlflow_run_id"] = None

    pending = filter_ungraded_predictions(prediction_log, existing_grades)
    graded = grade_predictions(pending, schedule_grading)
    if graded.empty:
        print(f"Week {week}: predicted {len(prediction_log)} games; no scores to grade")
        continue

    grading_run_id = new_grading_run_id()
    graded["grading_run_id"] = grading_run_id
    metrics = summarize_prediction_accuracy(graded)

    if log_grades:
        append_delta_table(spark, graded, grades_table)
        existing_grades = pd.concat([existing_grades, graded], ignore_index=True)

        with mlflow.start_run(run_name=f"backtest_grades_{season}_wk{week}") as run:
            mlflow.log_params(
                {
                    "season": season,
                    "week": week,
                    "grading_run_id": grading_run_id,
                    "prediction_run_id": prediction_run_id,
                    "backtest": True,
                }
            )
            mlflow.log_metrics(metrics)

    season_graded_frames.append(graded)
    week_summaries.append({"week": week, **metrics})
    spread_acc = metrics.get("spread_accuracy")
    total_acc = metrics.get("total_accuracy")
    spread_pct = f"{spread_acc * 100:.1f}%" if spread_acc is not None else "n/a"
    total_pct = f"{total_acc * 100:.1f}%" if total_acc is not None else "n/a"
    print(
        f"Week {week}: {len(graded)} graded | "
        f"spread {spread_pct} | total {total_pct}"
    )

# COMMAND ----------

if not season_graded_frames:
    print("No games graded; nothing to summarize.")
    dbutils.notebook.exit("SKIPPED")

season_graded = pd.concat(season_graded_frames, ignore_index=True)
season_metrics = summarize_prediction_accuracy(season_graded)

print(f"\nSeason {season} backtest summary ({len(season_graded)} games):")
for key, value in sorted(season_metrics.items()):
    if key.endswith("accuracy"):
        print(f"  {key}: {value * 100:.1f}%")
    else:
        print(f"  {key}: {value}")

summary_df = pd.DataFrame(week_summaries).sort_values("week")
display(spark.createDataFrame(summary_df))
display(spark.createDataFrame(season_graded))