"""Smoke-test Databricks Connect (serverless) for this project."""

from __future__ import annotations

import os
import sys


def _profile() -> str:
    for key in ("DATABRICKS_CONFIG_PROFILE", "databricks_profile"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def main() -> int:
    cluster_id = os.environ.get("DATABRICKS_CLUSTER_ID", "").strip()
    serverless_id = os.environ.get("DATABRICKS_SERVERLESS_COMPUTE_ID", "").strip()
    if cluster_id and serverless_id:
        print(
            "ERROR: DATABRICKS_CLUSTER_ID and DATABRICKS_SERVERLESS_COMPUTE_ID are both set.",
            file=sys.stderr,
        )
        print(
            "Clear DATABRICKS_CLUSTER_ID (User env / .env) when using serverless compute.",
            file=sys.stderr,
        )
        return 1

    profile = _profile()
    if not profile:
        print(
            "ERROR: Set DATABRICKS_CONFIG_PROFILE or databricks_profile in .env.",
            file=sys.stderr,
        )
        return 1

    try:
        from databricks.connect import DatabricksSession
    except ImportError:
        print("ERROR: databricks-connect is not installed in this environment.", file=sys.stderr)
        print("Run: pip install databricks-connect", file=sys.stderr)
        return 1

    spark = DatabricksSession.builder.profile(profile).getOrCreate()
    row = spark.sql("SELECT 1 AS ok").collect()[0]
    print(f"Connected (Spark {spark.version}, profile={profile!r}, row={row.ok})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())