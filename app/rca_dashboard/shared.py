"""SQL warehouse helpers for the RCA dashboard app."""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from databricks import sql
from databricks.sdk.core import Config


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


CATALOG = env("NFL_CATALOG", "nfl")
PREDICTIONS_SCHEMA = env("NFL_PREDICTIONS_SCHEMA", "predictions")
DEFAULT_SEASON = int(env("NFL_SCHEDULE_SEASON", "2026"))


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


def sql_query(query: str) -> pd.DataFrame:
    cfg = Config()
    with sql.connect(
        server_hostname=cfg.host,
        http_path=f"/sql/1.0/warehouses/{warehouse_id()}",
        credentials_provider=lambda: cfg.authenticate,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall_arrow().to_pandas()