"""Deploy nfl.predictions.game_pick_metrics Unity Catalog metric view."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRADES_TABLE_SQL = ROOT / "scripts" / "create_prediction_grades_table.sql"
METRIC_VIEW_SQL = ROOT / "scripts" / "create_mv_game_pick_metrics.sql"
DEFAULT_WAREHOUSE_ID = "abae422499df211c"


def _profile() -> str:
    env_path = ROOT / ".databricks" / ".databricks.env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABRICKS_CONFIG_PROFILE="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("DATABRICKS_CONFIG_PROFILE", "wyatts_databricks")


def _warehouse_id() -> str:
    return os.environ.get("DATABRICKS_WAREHOUSE_ID", DEFAULT_WAREHOUSE_ID)


def _execute_sql(statement: str, *, label: str) -> dict:
    payload = {
        "warehouse_id": _warehouse_id(),
        "statement": statement,
        "wait_timeout": "50s",
    }
    profile = _profile()
    cmd = [
        "databricks",
        "api",
        "post",
        "/api/2.0/sql/statements",
        "--profile",
        profile,
        "--json",
        json.dumps(payload),
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)

    response = json.loads(result.stdout)
    status = response.get("status", {})
    state = status.get("state")
    if state != "SUCCEEDED":
        error = status.get("error", {})
        raise SystemExit(f"{label} failed ({state}): {error.get('message', response)}")
    return response


def main() -> None:
    for path in (GRADES_TABLE_SQL, METRIC_VIEW_SQL):
        if not path.exists():
            raise SystemExit(f"Missing SQL file: {path}")

    schema_response = _execute_sql(
        "CREATE SCHEMA IF NOT EXISTS nfl.predictions",
        label="predictions schema create",
    )
    print("Ensured nfl.predictions schema exists")
    print(f"statement_id: {schema_response.get('statement_id')}")

    grades_response = _execute_sql(
        GRADES_TABLE_SQL.read_text(encoding="utf-8"),
        label="prediction_grades table create",
    )
    print("Ensured nfl.predictions.prediction_grades exists")
    print(f"statement_id: {grades_response.get('statement_id')}")

    view_response = _execute_sql(
        METRIC_VIEW_SQL.read_text(encoding="utf-8"),
        label="game_pick_metrics metric view deploy",
    )
    print("Deployed nfl.predictions.game_pick_metrics")
    print(f"statement_id: {view_response.get('statement_id')}")


if __name__ == "__main__":
    main()