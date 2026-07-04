"""Delete prediction and grade rows for a season (UC via Databricks Connect)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from test_databricks_connect import _load_project_env, _profile

_load_project_env()
profile = _profile()
if not profile:
    raise SystemExit("Set DATABRICKS_CONFIG_PROFILE in .env")

season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025

from databricks.connect import DatabricksSession

spark = DatabricksSession.builder.profile(profile).getOrCreate()

for table in ("nfl.predictions.game_predictions", "nfl.predictions.prediction_grades"):
    if not spark.catalog.tableExists(table):
        print(f"Skip {table} (missing)")
        continue
    before = spark.table(table).where(f"season = {season}").count()
    spark.sql(f"DELETE FROM {table} WHERE season = {season}")
    print(f"Deleted {before} rows from {table} where season = {season}")