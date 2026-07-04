# Databricks notebook source
# MAGIC %md
# MAGIC # Grade elapsed week
# MAGIC Compare latest predictions to final scores for the most recently completed week.
# MAGIC Appends to `nfl.predictions.prediction_grades` and logs accuracy to MLflow.

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
dbutils.widgets.dropdown("log_grades", "true", ["true", "false"], "Append grades to Delta")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    schedules=dbutils.widgets.get("schedules_schema"),
    predictions=dbutils.widgets.get("predictions_schema"),
)
season_raw = dbutils.widgets.get("season").strip()
target_week_raw = dbutils.widgets.get("target_week").strip()
mlflow_experiment = dbutils.widgets.get("mlflow_experiment").strip()
log_grades = dbutils.widgets.get("log_grades").lower() == "true"

predictions_table = paths.game_predictions_table()
grades_table = paths.prediction_grades_table()
schedule_table = paths.schedules_games_table()

print(f"Predictions: {predictions_table}")
print(f"Grades:      {grades_table}")
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

latest_run_id = select_latest_prediction_run(
    week_predictions,
    season=season,
    week=target_week,
)
if latest_run_id:
    week_predictions = week_predictions[
        week_predictions["prediction_run_id"] == latest_run_id
    ].copy()
    print(f"Using prediction_run_id: {latest_run_id}")

week_predictions = select_latest_predictions_per_game(week_predictions)

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