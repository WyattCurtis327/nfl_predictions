# Databricks notebook source
# MAGIC %md
# MAGIC # Apply Unity Catalog column descriptions
# MAGIC Re-applies table and column comments from `resources/schema` after bootstrap loads.

# COMMAND ----------

from nfl_predictions.uc_paths import (
    DEFAULT_CATALOG,
    DEFAULT_ODDS_SCHEMA,
    DEFAULT_PBP_SCHEMA,
    DEFAULT_PLAYERS_SCHEMA,
    DEFAULT_ROSTERS_SCHEMA,
    DEFAULT_SCHEDULES_SCHEMA,
    DEFAULT_TEAMS_SCHEMA,
    UcPaths,
)

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("teams_schema", DEFAULT_TEAMS_SCHEMA, "Teams schema")
dbutils.widgets.text("schedules_schema", DEFAULT_SCHEDULES_SCHEMA, "Schedules schema")
dbutils.widgets.text("pbp_schema", DEFAULT_PBP_SCHEMA, "PBP schema")
dbutils.widgets.text("rosters_schema", DEFAULT_ROSTERS_SCHEMA, "Rosters schema")
dbutils.widgets.text("players_schema", DEFAULT_PLAYERS_SCHEMA, "Players schema")
dbutils.widgets.text("odds_schema", DEFAULT_ODDS_SCHEMA, "Odds schema")
dbutils.widgets.text("schema_dir", "", "Workspace path to resources/schema")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    teams=dbutils.widgets.get("teams_schema"),
    schedules=dbutils.widgets.get("schedules_schema"),
    pbp=dbutils.widgets.get("pbp_schema"),
    rosters=dbutils.widgets.get("rosters_schema"),
    players=dbutils.widgets.get("players_schema"),
    odds=dbutils.widgets.get("odds_schema"),
)
schema_dir = dbutils.widgets.get("schema_dir").strip()

# COMMAND ----------

from pathlib import PurePosixPath

from nfl_predictions.uc_schema import apply_schema_directory, list_schema_files


def _default_schema_dir() -> str:
    notebook_path = (
        dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    )
    parts = [part for part in notebook_path.split("/") if part]
    if "notebooks" not in parts:
        raise ValueError(
            "schema_dir widget is required when notebook path does not include /notebooks/"
        )
    idx = parts.index("notebooks")
    return "/" + "/".join(parts[:idx] + ["resources", "schema"])


if not schema_dir:
    schema_dir = _default_schema_dir()

schema_files = list_schema_files(schema_dir)
if not schema_files:
    raise FileNotFoundError(f"No schema metadata files found under {schema_dir}")

print(f"Applying UC comments from {schema_dir}")
print(f"Catalog: {paths.catalog}")
print(f"Tables: {len(schema_files)}")

# COMMAND ----------

summaries = apply_schema_directory(spark, schema_dir, paths=paths)

rows = []
for summary in summaries:
    rows.append(
        {
            "table": summary.table,
            "table_comment_applied": summary.table_comment_applied,
            "column_comments_applied": summary.column_comments_applied,
            "column_comments_skipped": summary.column_comments_skipped,
            "errors": "; ".join(summary.errors),
        }
    )

import pandas as pd

result = pd.DataFrame(rows)
display(result)

failed = [summary for summary in summaries if summary.errors]
if failed:
    details = ", ".join(f"{summary.table} ({len(summary.errors)} errors)" for summary in failed)
    raise RuntimeError(f"Failed to apply UC column descriptions for: {details}")

total_applied = int(result["column_comments_applied"].sum())
print(f"Applied {total_applied:,} column comments across {len(summaries)} tables.")