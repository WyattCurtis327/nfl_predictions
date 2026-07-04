"""Deploy the Databricks bundle using local environment variables."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deploy_mv_game_pick_metrics import deploy_metric_view
from sync_bundle_env import ENV_FILE, _notify_email, _parse_env_file, _profile, sync_from_env_file


def main() -> None:
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    flags = set(sys.argv[1:])
    target = args[0] if args else "prod"

    if not ENV_FILE.exists():
        raise SystemExit(
            f"Missing {ENV_FILE}. Copy .env.example to .env and fill in your values."
        )

    sync_from_env_file()

    env_values = _parse_env_file(ENV_FILE)
    merged = {**env_values, **os.environ}
    profile = _profile(merged)
    notify_email = _notify_email(merged)

    if not profile:
        raise SystemExit(
            "Set DATABRICKS_CONFIG_PROFILE or databricks_profile in .env, e.g.\n"
            "  DATABRICKS_CONFIG_PROFILE=DEFAULT"
        )
    if not notify_email:
        raise SystemExit(
            "Set DATABRICKS_EMAIL_ACCOUNT in .env before deploying, e.g.\n"
            "  DATABRICKS_EMAIL_ACCOUNT=you@example.com"
        )
    if not merged.get("DATABRICKS_WAREHOUSE_ID", "").strip():
        raise SystemExit(
            "Set DATABRICKS_WAREHOUSE_ID in .env before deploying "
            "(required for Genie space and weekly picks app)."
        )

    env = os.environ.copy()
    env["DATABRICKS_CONFIG_PROFILE"] = profile
    env["BUNDLE_VAR_notify_email"] = notify_email
    env.pop("DATABRICKS_CLUSTER_ID", None)
    env.pop("BUNDLE_VAR_failure_notifications", None)

    cmd = [
        "databricks",
        "bundle",
        "deploy",
        "-t",
        target,
        "--profile",
        profile,
        "--auto-approve",
    ]
    subprocess.run(cmd, check=True, env=env)

    if "--skip-metric-view" not in flags:
        print("Deploying game_pick_metrics view...")
        deploy_metric_view()


if __name__ == "__main__":
    main()