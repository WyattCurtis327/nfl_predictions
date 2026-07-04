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
    DEFAULT_PREDICTIONS_SCHEMA,
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
dbutils.widgets.text("predictions_schema", DEFAULT_PREDICTIONS_SCHEMA, "Predictions schema")
dbutils.widgets.text("only_schema", "", "Apply only this canonical schema (e.g. predictions)")
dbutils.widgets.dropdown("skip_missing_tables", "false", ["true", "false"], "Skip tables that do not exist")
dbutils.widgets.text("schema_dir", "", "Workspace path to resources/schema")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    teams=dbutils.widgets.get("teams_schema"),
    schedules=dbutils.widgets.get("schedules_schema"),
    pbp=dbutils.widgets.get("pbp_schema"),
    rosters=dbutils.widgets.get("rosters_schema"),
    players=dbutils.widgets.get("players_schema"),
    odds=dbutils.widgets.get("odds_schema"),
    predictions=dbutils.widgets.get("predictions_schema"),
)
only_schema = dbutils.widgets.get("only_schema").strip() or None
skip_missing_tables = dbutils.widgets.get("skip_missing_tables").lower() == "true"
schema_dir = dbutils.widgets.get("schema_dir").strip()

# COMMAND ----------

import os

from nfl_predictions.uc_schema import apply_schema_directory, resolve_schema_directory


def _schema_dir_candidates(explicit: str) -> list[str]:
    candidates: list[str] = []
    if explicit:
        candidates.append(explicit)

    notebook_path = (
        dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    )
    parts = [part for part in notebook_path.split("/") if part]
    if "notebooks" in parts:
        idx = parts.index("notebooks")
        bundle_schema = "/" + "/".join(parts[:idx] + ["resources", "schema"])
        candidates.extend(
            [
                os.path.abspath(os.path.join(os.getcwd(), "..", "resources", "schema")),
                os.path.abspath(os.path.join(os.getcwd(), "resources", "schema")),
                bundle_schema,
                f"/Workspace{bundle_schema}",
            ]
        )
    else:
        candidates.append(os.path.abspath(os.path.join(os.getcwd(), "resources", "schema")))

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            ordered.append(candidate)
    return ordered


schema_candidates = _schema_dir_candidates(schema_dir)
resolved_schema_dir = resolve_schema_directory(schema_candidates[0], extra_candidates=schema_candidates[1:])

print(f"Applying UC comments from {resolved_schema_dir}")
print(f"Catalog: {paths.catalog}")

# COMMAND ----------

summaries = apply_schema_directory(
    spark,
    resolved_schema_dir,
    paths=paths,
    only_canonical_schema=only_schema,
    skip_missing_tables=skip_missing_tables,
)

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