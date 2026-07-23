# Databricks notebook source
# MAGIC %md
# MAGIC # Grade elapsed week
# MAGIC Compare latest predictions to final scores for the most recently completed week.
# MAGIC Appends to `nfl.gold.prediction_grades` and logs accuracy to MLflow.

# COMMAND ----------

from nfl_predictions.uc_paths import (
    DEFAULT_CATALOG,
    DEFAULT_PREDICTIONS_SCHEMA,
    DEFAULT_SCHEDULES_SCHEMA,
    UcPaths,
)

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("schedules_schema", DEFAULT_SCHEDULES_SCHEMA, "Schedules schema")
dbutils.widgets.text("predictions_schema", DEFAULT_PREDICTIONS_SCHEMA, "Predictions schema")
dbutils.widgets.text("season", "", "Season to grade (blank = auto-detect)")
dbutils.widgets.text("target_week", "", "Week to grade (blank = latest completed)")
dbutils.widgets.text("mlflow_experiment", "/Shared/nfl_predictions", "MLflow experiment path")
dbutils.widgets.text("model_id", "monte_carlo", "Model to grade (blank = all models in latest run)")
dbutils.widgets.dropdown("log_grades", "true", ["true", "false"], "Append grades to Delta")
dbutils.widgets.dropdown("log_rca", "true", ["true", "false"], "Analyze missed picks and append RCA")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    schedules=dbutils.widgets.get("schedules_schema"),
    predictions=dbutils.widgets.get("predictions_schema"),
)
season_raw = dbutils.widgets.get("season").strip()
target_week_raw = dbutils.widgets.get("target_week").strip()
mlflow_experiment = dbutils.widgets.get("mlflow_experiment").strip()
model_id_raw = dbutils.widgets.get("model_id").strip()
model_id = model_id_raw or None
log_grades = dbutils.widgets.get("log_grades").lower() == "true"
log_rca = dbutils.widgets.get("log_rca").lower() == "true"

predictions_table = paths.game_predictions_table()
grades_table = paths.prediction_grades_table()
rca_table = paths.prediction_rca_table()
pbp_table = paths.pbp_table()
schedule_table = paths.schedules_games_table()

print(f"Predictions: {predictions_table}")
print(f"Grades:      {grades_table}")
print(f"RCA:         {rca_table}")
print(f"PBP:         {pbp_table}")
print(f"Schedule:    {schedule_table}")

# COMMAND ----------

import pandas as pd

from nfl_predictions.simulation import (
    filter_schedule_game_types,
    filter_ungraded_predictions,
    grade_predictions,
    infer_latest_completed_week,
    new_grading_run_id,
    prepare_schedule_for_grading,
    select_latest_prediction_run,
    select_latest_predictions_per_game,
    summarize_prediction_accuracy,
)
from nfl_predictions.spark_io import append_delta_table

schedule_pdf = filter_schedule_game_types(spark.table(schedule_table).toPandas())
schedule_pdf = prepare_schedule_for_grading(schedule_pdf)

if season_raw:
    season = int(season_raw)
else:
    completed = schedule_pdf.dropna(subset=["home_score", "away_score"])
    season = int(completed["season"].max()) if not completed.empty else None
    if season is None:
        print("No completed games found; skipping grading.")
        dbutils.notebook.exit("SKIPPED")

schedule_season = schedule_pdf[schedule_pdf["season"] == season].copy()

if target_week_raw:
    target_week = int(target_week_raw)
else:
    target_week = infer_latest_completed_week(schedule_season, season=season)

if target_week is None:
    print(f"No completed week found for season {season}; skipping grading.")
    dbutils.notebook.exit("SKIPPED")

print(f"Grading season {season} week {target_week}")

# COMMAND ----------

if spark.catalog.tableExists(predictions_table):
    predictions_pdf = spark.table(predictions_table).toPandas()
else:
    predictions_pdf = pd.DataFrame()

if predictions_pdf.empty:
    print(f"No predictions in {predictions_table}; skipping grading.")
    dbutils.notebook.exit("SKIPPED")

week_predictions = predictions_pdf[
    (predictions_pdf["season"] == season) & (predictions_pdf["week"] == target_week)
].copy()

if week_predictions.empty:
    print(f"No predictions for season={season}, week={target_week}; skipping grading.")
    dbutils.notebook.exit("SKIPPED")

if model_id:
    week_predictions = week_predictions[
        week_predictions["model_id"].fillna("monte_carlo") == model_id
    ].copy()
    if week_predictions.empty:
        print(f"No predictions for model_id={model_id}; skipping grading.")
        dbutils.notebook.exit("SKIPPED")

latest_run_id = select_latest_prediction_run(
    week_predictions,
    season=season,
    week=target_week,
    model_id=model_id,
)
if latest_run_id:
    week_predictions = week_predictions[
        week_predictions["prediction_run_id"] == latest_run_id
    ].copy()
    print(f"Using prediction_run_id: {latest_run_id}")

week_predictions = select_latest_predictions_per_game(
    week_predictions,
    model_id=model_id,
)

existing_grades = (
    spark.table(grades_table).toPandas()
    if spark.catalog.tableExists(grades_table)
    else pd.DataFrame()
)
pending_predictions = filter_ungraded_predictions(week_predictions, existing_grades)

if pending_predictions.empty:
    print("All predictions for this week are already graded.")
    dbutils.notebook.exit("SKIPPED")

graded = grade_predictions(pending_predictions, schedule_season)
if graded.empty:
    print(
        f"No completed games with scores found for season={season}, week={target_week}."
    )
    dbutils.notebook.exit("SKIPPED")

grading_run_id = new_grading_run_id()
graded["grading_run_id"] = grading_run_id

metrics = summarize_prediction_accuracy(graded)
print("Accuracy metrics:")
for key, value in sorted(metrics.items()):
    if key.endswith("accuracy"):
        print(f"  {key}: {value * 100:.1f}%")
    else:
        print(f"  {key}: {value}")

display(spark.createDataFrame(graded))

# COMMAND ----------

if not log_grades:
    print("log_grades=false; skipped Delta + MLflow write")
else:
    import mlflow

    append_delta_table(spark, graded, grades_table)

    mlflow.set_experiment(mlflow_experiment)
    with mlflow.start_run(run_name=f"grades_{season}_wk{target_week}") as run:
        mlflow.log_params(
            {
                "season": season,
                "week": target_week,
                "grading_run_id": grading_run_id,
                "prediction_run_id": latest_run_id or "",
            }
        )
        mlflow.log_metrics(metrics)

    print(f"Appended {len(graded)} grades to {grades_table}")
    print(f"grading_run_id: {grading_run_id}")

# COMMAND ----------

from nfl_predictions.nfelo import nfelo_ratings_lookup, select_nfelo_ratings
from nfl_predictions.prediction_rca import (
    analyze_missed_grades,
    filter_missed_grades,
    new_rca_run_id,
    prepare_rca_log,
)

missed = filter_missed_grades(graded)
if missed.empty:
    print("No missed picks to analyze.")
elif not log_rca:
    print("log_rca=false; skipped RCA write")
else:
    pbp_pdf = spark.table(pbp_table).toPandas() if spark.catalog.tableExists(pbp_table) else pd.DataFrame()

    game_ids = set(missed["game_id"].dropna().astype(str))
    game_pbp_by_id: dict[str, pd.DataFrame] = {}
    if not pbp_pdf.empty and "game_id" in pbp_pdf.columns:
        game_rows = pbp_pdf[pbp_pdf["game_id"].astype(str).isin(game_ids)]
        for game_id, frame in game_rows.groupby("game_id"):
            game_pbp_by_id[str(game_id)] = frame.reset_index(drop=True)

    nfelo_games = pd.DataFrame()
    nfelo_lookup: dict[str, float] = {}
    ratings_table = paths.nfelo_ratings_table()
    games_table = paths.nfelo_games_table()
    if spark.catalog.tableExists(ratings_table):
        nfelo_lookup = nfelo_ratings_lookup(
            select_nfelo_ratings(
                spark.table(ratings_table).toPandas(),
                season=season,
                week=target_week,
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
    rca_log = prepare_rca_log(
        rca_reports,
        rca_run_id=rca_run_id,
        grading_run_id=grading_run_id,
    )
    append_delta_table(spark, rca_log, rca_table)
    print(f"Appended {len(rca_log)} RCA rows to {rca_table}")
    print(f"rca_run_id: {rca_run_id}")
    display(spark.createDataFrame(rca_log))