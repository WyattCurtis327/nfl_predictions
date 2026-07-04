"""Pull Unity Catalog table and column comments into local schema files."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

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

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "resources" / "schema"
ENV_FILE = REPO_ROOT / ".env"


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _profile(explicit: str | None) -> str:
    if explicit:
        return explicit

    env = {**_parse_env_file(ENV_FILE), **os.environ}
    for key in ("DATABRICKS_CONFIG_PROFILE", "databricks_profile"):
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def _fetch_table(full_name: str, profile: str) -> dict:
    cmd = ["databricks", "tables", "get", full_name, "-o", "json"]
    if profile:
        cmd[1:1] = ["--profile", profile]

    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())

    payload = json.loads(result.stdout)
    if isinstance(payload, list):
        if not payload:
            raise RuntimeError(f"No metadata returned for {full_name}")
        payload = payload[0]
    return payload


def _normalize_table_metadata(full_name: str, payload: dict) -> dict:
    columns = []
    for column in payload.get("columns", []):
        columns.append(
            {
                "name": column.get("name"),
                "type": column.get("type_text") or column.get("type_name"),
                "nullable": column.get("nullable"),
                "comment": (column.get("comment") or "").strip(),
            }
        )

    return {
        "table": payload.get("full_name") or full_name,
        "comment": (payload.get("comment") or "").strip(),
        "columns": columns,
    }


def _output_path(output_dir: Path, full_name: str) -> Path:
    catalog, schema, table = full_name.split(".", 2)
    return output_dir / catalog / schema / f"{table}.json"


def pull_tables(
    tables: list[str],
    *,
    output_dir: Path,
    profile: str,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for full_name in tables:
        metadata = _normalize_table_metadata(full_name, _fetch_table(full_name, profile))
        path = _output_path(output_dir, full_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        written.append(path)
        commented = sum(1 for col in metadata["columns"] if col["comment"])
        print(f"Wrote {path.relative_to(REPO_ROOT)} ({commented}/{len(metadata['columns'])} column comments)")

    manifest = {
        "catalog": tables[0].split(".", 1)[0] if tables else paths.catalog,
        "tables": [table for table in tables],
        "files": [str(path.relative_to(output_dir)).replace("\\", "/") for path in written],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    written.append(manifest_path)
    print(f"Wrote {manifest_path.relative_to(REPO_ROOT)}")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for pulled schema YAML files",
    )
    parser.add_argument(
        "--table",
        action="append",
        dest="tables",
        help="Fully qualified table name (repeatable). Defaults to bootstrap tables.",
    )
    parser.add_argument("--profile", help="Databricks CLI profile")
    parser.add_argument("--catalog", default=DEFAULT_CATALOG, help="Unity Catalog name")
    parser.add_argument("--teams-schema", default=DEFAULT_TEAMS_SCHEMA)
    parser.add_argument("--schedules-schema", default=DEFAULT_SCHEDULES_SCHEMA)
    parser.add_argument("--pbp-schema", default=DEFAULT_PBP_SCHEMA)
    parser.add_argument("--rosters-schema", default=DEFAULT_ROSTERS_SCHEMA)
    parser.add_argument("--players-schema", default=DEFAULT_PLAYERS_SCHEMA)
    parser.add_argument("--odds-schema", default=DEFAULT_ODDS_SCHEMA)
    args = parser.parse_args()

    profile = _profile(args.profile)
    paths = UcPaths(
        catalog=args.catalog,
        teams=args.teams_schema,
        schedules=args.schedules_schema,
        pbp=args.pbp_schema,
        rosters=args.rosters_schema,
        players=args.players_schema,
        odds=args.odds_schema,
    )
    tables = args.tables or paths.bootstrap_tables()

    try:
        pull_tables(tables, output_dir=args.output_dir, profile=profile)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())