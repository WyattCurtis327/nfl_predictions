# Databricks notebook source
# MAGIC %md
# MAGIC # Predict upcoming week
# MAGIC Monte Carlo spread and total picks for the next unplayed REG/playoff week.
# MAGIC Appends to `nfl.predictions.game_predictions` and logs to MLflow.

# COMMAND ----------

from nfl_predictions.uc_paths import (
    DEFAULT_CATALOG,
    DEFAULT_ODDS_SCHEMA,
    DEFAULT_PBP_SCHEMA,
    DEFAULT_PREDICTIONS_SCHEMA,
    DEFAULT_SCHEDULES_SCHEMA,
    UcPaths,
)

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("schedules_schema", DEFAULT_SCHEDULES_SCHEMA, "Schedules schema")
dbutils.widgets.text("pbp_schema", DEFAULT_PBP_SCHEMA, "PBP schema")
dbutils.widgets.text("odds_schema", DEFAULT_ODDS_SCHEMA, "Odds schema")
dbutils.widgets.text("predictions_schema", DEFAULT_PREDICTIONS_SCHEMA, "Predictions schema")
dbutils.widgets.text("season", "2026", "Schedule / odds season")
dbutils.widgets.text("pbp_season", "2025", "Prior-season PBP analytics")
dbutils.widgets.text("current_pbp_season", "2026", "In-season PBP analytics")
dbutils.widgets.text("target_week", "", "Week to simulate (blank = next unplayed)")
dbutils.widgets.text("n_simulations", "10000", "Monte Carlo simulations per game")
dbutils.widgets.text("market_blend", "0.35", "Weight given to market lines (0-1)")
dbutils.widgets.text("pick_threshold", "0.55", "Min confidence to highlight a pick")
dbutils.widgets.text("preferred_bookmaker", "draftkings", "Preferred bookmaker for odds")
dbutils.widgets.text("mlflow_experiment", "/Shared/nfl_predictions", "MLflow experiment path")
dbutils.widgets.dropdown("log_predictions", "true", ["true", "false"], "Append predictions")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    schedules=dbutils.widgets.get("schedules_schema"),
    pbp=dbutils.widgets.get("pbp_schema"),
    odds=dbutils.widgets.get("odds_schema"),
    predictions=dbutils.widgets.get("predictions_schema"),
)
season = int(dbutils.widgets.get("season"))
pbp_season = int(dbutils.widgets.get("pbp_season"))
current_pbp_season = int(dbutils.widgets.get("current_pbp_season"))
target_week_raw = dbutils.widgets.get("target_week").strip()
n_simulations = int(dbutils.widgets.get("n_simulations"))
market_blend = float(dbutils.widgets.get("market_blend"))
pick_threshold = float(dbutils.widgets.get("pick_threshold"))
preferred_bookmaker = dbutils.widgets.get("preferred_bookmaker").strip()
mlflow_experiment = dbutils.widgets.get("mlflow_experiment").strip()
log_predictions = dbutils.widgets.get("log_predictions").lower() == "true"

pbp_table = paths.pbp_table()
odds_table = paths.game_odds_latest_table()
schedule_table = paths.schedules_games_table()
predictions_table = paths.game_predictions_table()

print(f"PBP:          {pbp_table}")
print(f"Odds:         {odds_table}")
print(f"Schedule:     {schedule_table}")
print(f"Predictions:  {predictions_table}")

# COMMAND ----------

from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.simulation import (
    SimulationConfig,
    combine_pbp_seasons,
    compute_team_scoring_profiles,
    filter_schedule_game_types,
    infer_next_week,
    new_prediction_run_id,
    prepare_odds_for_simulation,
    prepare_prediction_log,
    simulate_weekly_picks,
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

if target_week_raw:
    target_week = int(target_week_raw)
else:
    target_week = infer_next_week(schedule_pdf, season=season)

if target_week is None:
    raise ValueError("No unplayed REG/playoff weeks found; set target_week explicitly.")

profiles = compute_team_scoring_profiles(pbp_pdf)
config = SimulationConfig(
    n_simulations=n_simulations,
    market_blend=market_blend,
    pick_threshold=pick_threshold,
)

print(f"Simulating season {season} week {target_week} with {n_simulations:,} runs per game")
print(f"Team scoring profiles: {len(profiles)} teams")

# COMMAND ----------

picks = simulate_weekly_picks(
    odds_pdf,
    profiles,
    week=target_week,
    schedule=schedule_pdf,
    config=config,
)

if picks.empty:
    raise ValueError(
        f"No odds rows found for week {target_week}. "
        "Refresh odds before running predictions."
    )

display(spark.createDataFrame(picks))

# COMMAND ----------

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
    source_file=f"predict_upcoming_week:{prediction_run_id}",
)

if not log_predictions:
    print("log_predictions=false; skipped Delta + MLflow write")
else:
    import mlflow

    mlflow.set_experiment(mlflow_experiment)
    with mlflow.start_run(run_name=f"predictions_{season}_wk{target_week}") as run:
        mlflow_run_id = run.info.run_id
        prediction_log["mlflow_run_id"] = mlflow_run_id

        mlflow.log_params(
            {
                "season": season,
                "week": target_week,
                "pbp_season": pbp_season,
                "current_pbp_season": current_pbp_season,
                "n_simulations": n_simulations,
                "market_blend": market_blend,
                "pick_threshold": pick_threshold,
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

        print(f"Logged {len(prediction_log)} predictions")
        print(f"prediction_run_id: {prediction_run_id}")
        print(f"mlflow_run_id: {mlflow_run_id}")
        print(f"delta table: {predictions_table}")