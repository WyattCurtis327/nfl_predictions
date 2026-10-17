"""Store The Odds API key in a Databricks secret scope."""

from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
DEFAULT_SCOPE = "nfl"
DEFAULT_KEY = "odds_api_key"


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


def _api_key(explicit: str | None) -> str:
    if explicit:
        return explicit.strip()

    env = {**_parse_env_file(ENV_FILE), **os.environ}
    for key in ("ODDS_API_KEY", "odds_api_key"):
        value = env.get(key, "").strip()
        if value:
            return value

    value = getpass.getpass("Odds API key (input hidden): ").strip()
    if not value:
        raise ValueError("Odds API key is required")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help="Databricks secret scope")
    parser.add_argument("--key", default=DEFAULT_KEY, help="Secret key name")
    parser.add_argument("--api-key", dest="api_key", help="Odds API key value")
    parser.add_argument("--profile", help="Databricks CLI profile")
    parser.add_argument(
        "--create-scope",
        action="store_true",
        help="Create the scope first if it does not exist",
    )
    args = parser.parse_args()

    profile = _profile(args.profile)
    api_key = _api_key(args.api_key)

    base_cmd = ["databricks"]
    if profile:
        base_cmd.extend(["--profile", profile])

    if args.create_scope:
        create = subprocess.run(
            [*base_cmd, "secrets", "create-scope", args.scope],
            capture_output=True,
            text=True,
            check=False,
        )
        if create.returncode != 0 and "RESOURCE_ALREADY_EXISTS" not in (create.stderr + create.stdout):
            print(create.stderr or create.stdout, file=sys.stderr)
            return create.returncode

    put = subprocess.run(
        [
            *base_cmd,
            "secrets",
            "put-secret",
            args.scope,
            args.key,
            "--string-value",
            api_key,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if put.returncode != 0:
        print(put.stderr or put.stdout, file=sys.stderr)
        return put.returncode

    print(f"Stored secret {args.scope}/{args.key}")
    print(
        "Use in notebooks: "
        f"dbutils.secrets.get(scope='{args.scope}', key='{args.key}')"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())