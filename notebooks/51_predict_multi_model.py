# Databricks notebook source
# MAGIC %md
# MAGIC # Predict upcoming week (multi-model)
# MAGIC Runs Monte Carlo plus alternative model families and appends to
# MAGIC `nfl.predictions.game_predictions` with distinct `model_id` values.

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
dbutils.widgets.text("season", "2026", "Schedule / odds season")
dbutils.widgets.text("pbp_season", "2025", "Prior-season PBP analytics")
dbutils.widgets.text("current_pbp_season", "2026", "In-season PBP analytics")
dbutils.widgets.text("target_week", "", "Week to simulate (blank = next unplayed)")
dbutils.widgets.text("n_simulations", "10000", "Monte Carlo simulations per game")
dbutils.widgets.text("market_blend", "0.35", "Weight given to market lines (0-1)")
dbutils.widgets.text("nfelo_blend", "0.30", "Weight given to nfelo ratings (0-1)")
dbutils.widgets.dropdown("use_nfelo", "true", ["true", "false"], "Blend nfelo power ratings")
dbutils.widgets.text("pick_threshold", "0.55", "Min confidence to highlight a pick")
dbutils.widgets.text("preferred_bookmaker", "draftkings", "Preferred bookmaker for odds")
dbutils.widgets.text(
    "model_ids",
    "monte_carlo,poisson,elo,epa_margin,line_relative,shrinkage_profile,situational_total,ensemble",
    "Comma-separated model_id values",
)
dbutils.widgets.text("mlflow_experiment", "/Shared/nfl_predictions", "MLflow experiment path")
dbutils.widgets.dropdown("log_predictions", "true", ["true", "false"], "Append predictions")

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
target_week_raw = dbutils.widgets.get("target_week").strip()
n_simulations = int(dbutils.widgets.get("n_simulations"))
market_blend = float(dbutils.widgets.get("market_blend"))
nfelo_blend = float(dbutils.widgets.get("nfelo_blend"))
use_nfelo = dbutils.widgets.get("use_nfelo").lower() == "true"
pick_threshold = float(dbutils.widgets.get("pick_threshold"))
preferred_bookmaker = dbutils.widgets.get("preferred_bookmaker").strip()
model_ids_raw = dbutils.widgets.get("model_ids").strip()
mlflow_experiment = dbutils.widgets.get("mlflow_experiment").strip()
log_predictions = dbutils.widgets.get("log_predictions").lower() == "true"

model_ids = tuple(
    part.strip()
    for part in model_ids_raw.split(",")
    if part.strip()
)

pbp_table = paths.pbp_table()
odds_table = paths.game_odds_latest_table()
schedule_table = paths.schedules_games_table()
predictions_table = paths.game_predictions_table()

print(f"PBP:          {pbp_table}")
print(f"Odds:         {odds_table}")
print(f"Schedule:     {schedule_table}")
print(f"Predictions:  {predictions_table}")
print(f"Models:       {model_ids}")

# COMMAND ----------

import pandas as pd

from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.models import ModelRunContext, run_all_models
from nfl_predictions.models.common import ModelConfig
from nfl_predictions.nfelo import select_nfelo_ratings
from nfl_predictions.simulation import (
    SimulationConfig,
    combine_pbp_seasons,
    compute_team_scoring_profiles,
    filter_schedule_game_types,
    infer_next_week,
    new_prediction_run_id,
    prepare_odds_for_simulation,
    prepare_prediction_log,
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
model_config = ModelConfig(pick_threshold=pick_threshold)
simulation_config = SimulationConfig(
    n_simulations=n_simulations,
    market_blend=market_blend,
    nfelo_blend=nfelo_blend if use_nfelo else 0.0,
    pick_threshold=pick_threshold,
)

nfelo_ratings = pd.DataFrame()
nfelo_games = pd.DataFrame()
if use_nfelo:
    ratings_table = paths.nfelo_ratings_table()
    games_table = paths.nfelo_games_table()
    if spark.catalog.tableExists(ratings_table):
        nfelo_ratings = select_nfelo_ratings(
            spark.table(ratings_table).toPandas(),
            season=season,
            week=target_week,
        )
    if spark.catalog.tableExists(games_table):
        nfelo_games = spark.table(games_table).toPandas()

ctx = ModelRunContext(
    odds_games=odds_pdf,
    profiles=profiles,
    week=target_week,
    schedule=schedule_pdf,
    pbp=pbp_pdf,
    training_odds=odds_pdf,
    config=model_config,
    simulation_config=simulation_config,
    nfelo_ratings=nfelo_ratings,
    nfelo_games=nfelo_games,
)

print(f"Simulating season {season} week {target_week}")
print(f"Team scoring profiles: {len(profiles)} teams")

# COMMAND ----------

picks = run_all_models(ctx, model_ids=model_ids)

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
    config=simulation_config,
)
prediction_log = stamp_dataframe(
    prediction_log,
    source_file=f"predict_multi_model:{prediction_run_id}",
)

if not log_predictions:
    print("log_predictions=false; skipped Delta + MLflow write")
else:
    import mlflow

    mlflow.set_experiment(mlflow_experiment)
    with mlflow.start_run(run_name=f"multi_model_{season}_wk{target_week}") as run:
        mlflow_run_id = run.info.run_id
        prediction_log["mlflow_run_id"] = mlflow_run_id

        model_counts = picks.groupby("model_id").size().to_dict()
        mlflow.log_params(
            {
                "season": season,
                "week": target_week,
                "pbp_season": pbp_season,
                "current_pbp_season": current_pbp_season,
                "n_simulations": n_simulations,
                "market_blend": market_blend,
                "nfelo_blend": simulation_config.nfelo_blend,
                "pick_threshold": pick_threshold,
                "prediction_run_id": prediction_run_id,
                "model_ids": ",".join(model_ids),
            }
        )
        mlflow.log_metrics(
            {
                "games_predicted": float(len(prediction_log)),
                "models_run": float(len(model_counts)),
                "avg_spread_confidence": float(
                    prediction_log["spread_confidence"].mean()
                ),
                "avg_total_confidence": float(
                    prediction_log["total_confidence"].mean()
                ),
            }
        )

        append_delta_table(spark, prediction_log, predictions_table)

        print(f"Logged {len(prediction_log)} predictions across {len(model_counts)} models")
        print(f"prediction_run_id: {prediction_run_id}")
        print(f"mlflow_run_id: {mlflow_run_id}")
        print(f"delta table: {predictions_table}")