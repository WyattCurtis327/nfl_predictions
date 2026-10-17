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
RCA_TABLE_SQL = SQL_DIR / "create_prediction_rca_table.sql"
PICK_MISS_RCA_VIEW_SQL = SQL_DIR / "create_vw_pick_miss_rca.sql"
METRIC_VIEW_SQL = SQL_DIR / "create_mv_game_pick_metrics.sql"
ALTER_MODEL_ID_SQL = SQL_DIR / "alter_game_predictions_add_model_id.sql"
DEFAULT_CATALOG = "nfl"
DEFAULT_PREDICTIONS_SCHEMA = "gold"


def _profile() -> str:
    env_path = ROOT / ".databricks" / ".databricks.env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABRICKS_CONFIG_PROFILE="):
                return line.split("=", 1)[1].strip()
    for key in ("DATABRICKS_CONFIG_PROFILE", "databricks_profile"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    raise SystemExit(
        "Set DATABRICKS_CONFIG_PROFILE in .env (run scripts/sync_bundle_env.py)."
    )


def _warehouse_id() -> str:
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "").strip()
    if not warehouse_id:
        raise SystemExit(
            "Set DATABRICKS_WAREHOUSE_ID in .env (SQL warehouse for metric view deploy)."
        )
    return warehouse_id


def _render_sql(path: Path, *, catalog: str, predictions_schema: str) -> str:
    return (
        path.read_text(encoding="utf-8")
        .replace("{catalog}", catalog)
        .replace("{predictions_schema}", predictions_schema)
    )


def _notify_email() -> str:
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABRICKS_EMAIL_ACCOUNT="):
                return line.split("=", 1)[1].strip()
    return os.environ.get("DATABRICKS_EMAIL_ACCOUNT", "").strip()


APP_NAMES = ("nfl-copilot", "nfl-rca-dashboard", "nfl-weekly-picks")


def _app_service_principals(profile: str) -> list[str]:
    principals: list[str] = []
    for app_name in APP_NAMES:
        cmd = [
            "databricks",
            "apps",
            "get",
            app_name,
            "--profile",
            profile,
            "-o",
            "json",
        ]
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            continue
        payload = json.loads(result.stdout)
        client_id = payload.get("service_principal_client_id", "").strip()
        if client_id:
            principals.append(client_id)
    return principals


def _grant_predictions_read_access(
    *,
    catalog: str,
    predictions_schema: str,
    principals: list[str],
) -> None:
    schema = f"{catalog}.{predictions_schema}"
    pbp_schema = os.environ.get("NFL_PBP_SCHEMA", "landing")
    objects = [
        ("TABLE", f"{schema}.prediction_grades"),
        ("TABLE", f"{schema}.prediction_rca"),
        ("TABLE", f"{schema}.game_predictions"),
        ("VIEW", f"{schema}.pick_miss_rca"),
        ("TABLE", f"{catalog}.{pbp_schema}.play_by_play"),
    ]
    for principal in principals:
        safe_principal = principal.replace("`", "")
        grants = [
            f"GRANT USE SCHEMA ON SCHEMA {schema} TO `{safe_principal}`",
            *[
                f"GRANT SELECT ON {object_type} {name} TO `{safe_principal}`"
                for object_type, name in objects
            ],
        ]
        for statement in grants:
            try:
                _execute_sql(statement, label=f"grant for {safe_principal}")
            except SystemExit as exc:
                print(f"Warning: grant skipped for {safe_principal}: {exc}")


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
    for path in (GRADES_TABLE_SQL, RCA_TABLE_SQL, PICK_MISS_RCA_VIEW_SQL, METRIC_VIEW_SQL):
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

    if ALTER_MODEL_ID_SQL.exists():
        rendered = _render_sql(
            ALTER_MODEL_ID_SQL,
            catalog=catalog,
            predictions_schema=predictions_schema,
        )
        for chunk in rendered.split(";"):
            lines = [
                line
                for line in chunk.splitlines()
                if line.strip() and not line.strip().startswith("--")
            ]
            stmt = "\n".join(lines).strip()
            if not stmt:
                continue
            try:
                alter_response = _execute_sql(stmt, label="model_id column alter")
            except SystemExit as exc:
                message = str(exc).lower()
                if "already exists" in message or "duplicate" in message:
                    print(f"Skipped (column exists): {stmt.splitlines()[0]}")
                    continue
                raise
            print(f"Applied: {stmt.splitlines()[0]}")
            print(f"statement_id: {alter_response.get('statement_id')}")

    rca_response = _execute_sql(
        _render_sql(RCA_TABLE_SQL, catalog=catalog, predictions_schema=predictions_schema),
        label="prediction_rca table create",
    )
    print(f"Ensured {catalog}.{predictions_schema}.prediction_rca exists")
    print(f"statement_id: {rca_response.get('statement_id')}")

    pick_miss_response = _execute_sql(
        _render_sql(PICK_MISS_RCA_VIEW_SQL, catalog=catalog, predictions_schema=predictions_schema),
        label="pick_miss_rca view deploy",
    )
    print(f"Deployed {catalog}.{predictions_schema}.pick_miss_rca")
    print(f"statement_id: {pick_miss_response.get('statement_id')}")

    view_response = _execute_sql(
        _render_sql(METRIC_VIEW_SQL, catalog=catalog, predictions_schema=predictions_schema),
        label="game_pick_metrics metric view deploy",
    )
    print(f"Deployed {catalog}.{predictions_schema}.game_pick_metrics")
    print(f"statement_id: {view_response.get('statement_id')}")

    principals: list[str] = []
    email = _notify_email()
    if email:
        principals.append(email)
    principals.extend(_app_service_principals(_profile()))
    unique_principals = list(dict.fromkeys(principals))
    if unique_principals:
        _grant_predictions_read_access(
            catalog=catalog,
            predictions_schema=predictions_schema,
            principals=unique_principals,
        )
        print(f"Granted predictions read access to: {', '.join(unique_principals)}")


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