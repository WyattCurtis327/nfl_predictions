"""Smoke-test Databricks Connect (serverless) for this project."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
VSCODE_ENV_FILE = REPO_ROOT / ".databricks" / ".databricks.env"

# VS Code writes these for its metadata-service auth proxy; they break CLI Connect.
_VSCODE_ONLY_KEYS = frozenset(
    {
        "DATABRICKS_AUTH_TYPE",
        "DATABRICKS_METADATA_SERVICE_URL",
        "DATABRICKS_PROJECT_ROOT",
        "DATABRICKS_BUNDLE_TARGET",
        "PYDEVD_WARN_SLOW_RESOLVE_TIMEOUT",
        "SPARK_CONNECT_PROGRESS_BAR_ENABLED",
        "SPARK_CONNECT_USER_AGENT",
    }
)


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _load_project_env() -> None:
    """Apply .env and VS Code Databricks env without overriding the shell."""
    for key, value in _parse_env_file(ENV_FILE).items():
        if value:
            os.environ.setdefault(key, value)

    for key, value in _parse_env_file(VSCODE_ENV_FILE).items():
        if not value or key in _VSCODE_ONLY_KEYS or key.startswith("BUNDLE_VAR_"):
            continue
        os.environ.setdefault(key, value)

    for key in _VSCODE_ONLY_KEYS:
        os.environ.pop(key, None)


def _profile() -> str:
    for key in ("DATABRICKS_CONFIG_PROFILE", "databricks_profile"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def main() -> int:
    _load_project_env()

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