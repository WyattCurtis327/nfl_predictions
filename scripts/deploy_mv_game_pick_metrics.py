"""Deploy predictions schema objects (grades table + game_pick_metrics view)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "resources" / "sql"
GRADES_TABLE_SQL = SQL_DIR / "create_prediction_grades_table.sql"
METRIC_VIEW_SQL = SQL_DIR / "create_mv_game_pick_metrics.sql"
DEFAULT_WAREHOUSE_ID = "abae422499df211c"
DEFAULT_CATALOG = "nfl"
DEFAULT_PREDICTIONS_SCHEMA = "predictions"


def _profile() -> str:
    env_path = ROOT / ".databricks" / ".databricks.env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABRICKS_CONFIG_PROFILE="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("DATABRICKS_CONFIG_PROFILE", "wyatts_databricks")


def _warehouse_id() -> str:
    return os.environ.get("DATABRICKS_WAREHOUSE_ID", DEFAULT_WAREHOUSE_ID)


def _render_sql(path: Path, *, catalog: str, predictions_schema: str) -> str:
    return (
        path.read_text(encoding="utf-8")
        .replace("{catalog}", catalog)
        .replace("{predictions_schema}", predictions_schema)
    )


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


def deploy_metric_view(
    *,
    catalog: str = DEFAULT_CATALOG,
    predictions_schema: str = DEFAULT_PREDICTIONS_SCHEMA,
) -> None:
    for path in (GRADES_TABLE_SQL, METRIC_VIEW_SQL):
        if not path.exists():
            raise SystemExit(f"Missing SQL file: {path}")

    schema_response = _execute_sql(
        f"CREATE SCHEMA IF NOT EXISTS {catalog}.{predictions_schema}",
        label="predictions schema create",
    )
    print(f"Ensured {catalog}.{predictions_schema} schema exists")
    print(f"statement_id: {schema_response.get('statement_id')}")

    grades_response = _execute_sql(
        _render_sql(GRADES_TABLE_SQL, catalog=catalog, predictions_schema=predictions_schema),
        label="prediction_grades table create",
    )
    print(f"Ensured {catalog}.{predictions_schema}.prediction_grades exists")
    print(f"statement_id: {grades_response.get('statement_id')}")

    view_response = _execute_sql(
        _render_sql(METRIC_VIEW_SQL, catalog=catalog, predictions_schema=predictions_schema),
        label="game_pick_metrics metric view deploy",
    )
    print(f"Deployed {catalog}.{predictions_schema}.game_pick_metrics")
    print(f"statement_id: {view_response.get('statement_id')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default=DEFAULT_CATALOG)
    parser.add_argument("--predictions-schema", default=DEFAULT_PREDICTIONS_SCHEMA)
    args = parser.parse_args()
    deploy_metric_view(
        catalog=args.catalog,
        predictions_schema=args.predictions_schema,
    )


if __name__ == "__main__":
    main()