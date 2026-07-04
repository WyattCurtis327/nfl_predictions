"""Shared Streamlit + SQL warehouse helpers for the weekly picks app."""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


CATALOG = env("NFL_CATALOG", "nfl")
PREDICTIONS_SCHEMA = env("NFL_PREDICTIONS_SCHEMA", "predictions")
DEFAULT_SEASON = int(env("NFL_SCHEDULE_SEASON", "2026"))


def predictions_table() -> str:
    return f"{CATALOG}.{PREDICTIONS_SCHEMA}.game_predictions"


def pick_miss_rca_view() -> str:
    return f"{CATALOG}.{PREDICTIONS_SCHEMA}.pick_miss_rca"


def _warehouse_id_from_app_resources() -> str:
    app_name = env("DATABRICKS_APP_NAME")
    if not app_name:
        return ""
    from databricks.sdk import WorkspaceClient

    app = WorkspaceClient().apps.get(app_name)
    for resource in app.resources or []:
        if resource.sql_warehouse and resource.sql_warehouse.id:
            return str(resource.sql_warehouse.id).strip()
    return ""


@st.cache_resource
def warehouse_id() -> str:
    wh_id = env("DATABRICKS_WAREHOUSE_ID") or _warehouse_id_from_app_resources()
    if not wh_id:
        st.error(
            "DATABRICKS_WAREHOUSE_ID is not set. Attach a SQL warehouse app resource "
            "named `sql-warehouse` and redeploy the bundle."
        )
        st.stop()
    return wh_id


_NUMERIC_TYPES = frozenset(
    {"DOUBLE", "FLOAT", "DECIMAL", "INT", "INTEGER", "BIGINT", "LONG", "SHORT", "BYTE"}
)
_BOOL_TYPES = frozenset({"BOOLEAN", "BOOL"})


def _column_type_name(column) -> str:
    raw = getattr(column, "type_name", None)
    if raw is None:
        return ""
    if hasattr(raw, "value"):
        raw = raw.value
    text = str(raw).strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.upper()


def _statement_to_dataframe(response) -> pd.DataFrame:
    if response.result is None or response.manifest is None:
        return pd.DataFrame()
    schema_columns = response.manifest.schema.columns
    columns = [col.name for col in schema_columns]
    rows = response.result.data_array or []
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows, columns=columns)
    for col in schema_columns:
        if col.name not in frame.columns:
            continue
        type_name = _column_type_name(col)
        if type_name in _NUMERIC_TYPES:
            frame[col.name] = pd.to_numeric(frame[col.name], errors="coerce")
        elif type_name in _BOOL_TYPES:
            frame[col.name] = frame[col.name].map(
                lambda value: value in (True, "true", "True", "1", 1) if pd.notna(value) else value
            )
    return frame


def _sql_query_via_app_identity(query: str, wh_id: str) -> pd.DataFrame:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import StatementState

    client = WorkspaceClient()
    response = client.statement_execution.execute_statement(
        warehouse_id=wh_id,
        statement=query,
        wait_timeout="50s",
    )
    state = response.status.state if response.status else None
    if state not in (StatementState.SUCCEEDED,):
        message = response.status.error.message if response.status and response.status.error else state
        raise RuntimeError(message)
    return _statement_to_dataframe(response)


def _sql_query_via_user_identity(query: str, wh_id: str) -> pd.DataFrame:
    from databricks import sql
    from databricks.sdk.core import Config

    cfg = Config()
    with sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{wh_id}",
        credentials_provider=lambda: cfg.authenticate,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall_arrow().to_pandas()


def sql_query(query: str) -> pd.DataFrame:
    wh_id = warehouse_id()
    if env("DATABRICKS_APP_NAME"):
        return _sql_query_via_app_identity(query, wh_id)
    return _sql_query_via_user_identity(query, wh_id)