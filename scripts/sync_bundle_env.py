"""Sync .env values into VS Code bundle env for Databricks deploy."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
BUNDLE_FILE = REPO_ROOT / "databricks.yml"
VSCODE_ENV_FILE = REPO_ROOT / ".databricks" / ".databricks.env"
DEFAULT_BUNDLE_TARGET = "prod"
STALE_SUBSTRINGS = (
    "BUNDLE_VAR_failure_notifications",
    "BUNDLE_VAR_databricks_profile",
)
# Written by the VS Code extension per session; stale values break CLI Connect.
_VSCODE_EPHEMERAL_KEYS = frozenset(
    {
        "DATABRICKS_AUTH_TYPE",
        "DATABRICKS_METADATA_SERVICE_URL",
        "DATABRICKS_PROJECT_ROOT",
        "PYDEVD_WARN_SLOW_RESOLVE_TIMEOUT",
        "SPARK_CONNECT_PROGRESS_BAR_ENABLED",
        "SPARK_CONNECT_USER_AGENT",
    }
)
_CONNECT_CONFLICT_KEYS = frozenset({"DATABRICKS_CLUSTER_ID"})


def _bundle_var_overrides_path(target: str = DEFAULT_BUNDLE_TARGET) -> Path:
    return REPO_ROOT / ".databricks" / "bundle" / target / "variable-overrides.json"


def _bundle_resources_path(target: str = DEFAULT_BUNDLE_TARGET) -> Path:
    return REPO_ROOT / ".databricks" / "bundle" / target / "resources.json"


_GENIE_VAR_ENV_KEYS = {
    "genie_pick_metrics_space_id": (
        "genie_pick_metrics_space_id",
        "NFL_GENIE_METRICS_SPACE_ID",
    ),
    "genie_pick_miss_rca_space_id": (
        "genie_pick_miss_rca_space_id",
        "NFL_GENIE_RCA_SPACE_ID",
    ),
}
_GENIE_APP_RESOURCE_NAMES = {
    "genie_pick_metrics_space_id": "nfl_game_pick_metrics",
    "genie_pick_miss_rca_space_id": "nfl_pick_miss_rca",
}


def _genie_space_ids_from_state(target: str = DEFAULT_BUNDLE_TARGET) -> dict[str, str]:
    """Read deployed Genie space IDs from local bundle state."""
    path = _bundle_resources_path(target)
    if not path.exists():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}

    resources = data.get("state", data)

    mapping = {
        "genie_pick_metrics_space_id": "resources.genie_spaces.nfl_game_pick_metrics",
        "genie_pick_miss_rca_space_id": "resources.genie_spaces.nfl_pick_miss_rca",
    }
    overrides: dict[str, str] = {}
    for var_name, resource_key in mapping.items():
        resource = resources.get(resource_key, {})
        space_id = str(resource.get("__id__", "")).strip()
        if space_id:
            overrides[var_name] = space_id
    return overrides


def _genie_space_ids_from_env(env: dict[str, str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for var_name, keys in _GENIE_VAR_ENV_KEYS.items():
        for key in keys:
            space_id = env.get(key, "").strip()
            if space_id:
                overrides[var_name] = space_id
                break
    return overrides


def _genie_space_ids_from_app(profile: str) -> dict[str, str]:
    """Fallback: read Genie space IDs already linked on the deployed nfl-copilot app."""
    if not profile:
        return {}

    cmd = [
        "databricks",
        "apps",
        "get",
        "nfl-copilot",
        "--profile",
        profile,
        "-o",
        "json",
    ]
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        return {}

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}

    by_name = {
        str(resource.get("genie_space", {}).get("name", "")).strip(): str(
            resource.get("genie_space", {}).get("space_id", "")
        ).strip()
        for resource in payload.get("resources", [])
        if resource.get("genie_space")
    }
    overrides: dict[str, str] = {}
    for var_name, genie_name in _GENIE_APP_RESOURCE_NAMES.items():
        space_id = by_name.get(genie_name, "")
        if space_id:
            overrides[var_name] = space_id
    return overrides


def _genie_space_ids(
    env: dict[str, str],
    *,
    target: str = DEFAULT_BUNDLE_TARGET,
    profile: str = "",
) -> dict[str, str]:
    """Resolve Genie space bundle vars (bundle state > .env > nfl-copilot app)."""
    merged: dict[str, str] = {}
    merged.update(_genie_space_ids_from_app(profile))
    merged.update(_genie_space_ids_from_env(env))
    merged.update(_genie_space_ids_from_state(target))
    return merged


def _workspace_host(profile: str) -> str:
    """Read https:// host from ~/.databrickscfg for the given profile."""
    cfg_path = Path.home() / ".databrickscfg"
    if not cfg_path.exists() or not profile:
        return ""

    section = ""
    host = ""
    for raw_line in cfg_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if section != profile or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "host":
            host = value.strip()
            break

    if not host:
        return ""
    if not host.startswith(("http://", "https://")):
        host = f"https://{host}"
    return host.rstrip("/") + "/"


def _sync_databricks_yml_workspace(host: str, profile: str) -> None:
    """Keep workspace.host and workspace.profile in databricks.yml aligned with .env.

    The VS Code extension parses bundle YAML directly and throws
    'Invalid host name' when workspace.host is missing.
    """
    if not BUNDLE_FILE.exists():
        return
    if not host and not profile:
        return

    text = BUNDLE_FILE.read_text(encoding="utf-8")
    updated = text

    if host:
        normalized = host.rstrip("/")
        host_line = f"      host: {normalized}"
        if re.search(r"^      host: ", updated, flags=re.MULTILINE):
            updated = re.sub(
                r"^      host: .*$",
                host_line,
                updated,
                flags=re.MULTILINE,
            )
        else:
            updated = updated.replace(
                "    workspace:\n      root_path:",
                f"    workspace:\n{host_line}\n      root_path:",
                1,
            )

    if profile:
        profile_line = f"      profile: {profile}"
        if re.search(r"^      profile: ", updated, flags=re.MULTILINE):
            updated = re.sub(
                r"^      profile: .*$",
                profile_line,
                updated,
                flags=re.MULTILINE,
            )
        elif re.search(r"^      host: ", updated, flags=re.MULTILINE):
            updated = re.sub(
                r"^(      host: .*)$",
                rf"\1\n{profile_line}",
                updated,
                flags=re.MULTILINE,
            )
        else:
            updated = updated.replace(
                "    workspace:\n      root_path:",
                f"    workspace:\n{profile_line}\n      root_path:",
                1,
            )

    if updated != text:
        BUNDLE_FILE.write_text(updated, encoding="utf-8")


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


def _notify_email(env: dict[str, str]) -> str:
    for key in ("DATABRICKS_EMAIL_ACCOUNT", "databricks_email_account"):
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def _profile(env: dict[str, str]) -> str:
    for key in ("DATABRICKS_CONFIG_PROFILE", "databricks_profile"):
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def _should_drop_env_key(key: str, *, vscode_env: bool = False) -> bool:
    if key in _CONNECT_CONFLICT_KEYS:
        return True
    # Only strip extension session keys from the project .env, not .databricks.env.
    if vscode_env:
        return False
    return key in _VSCODE_EPHEMERAL_KEYS


def _upsert_env_file(
    path: Path, updates: dict[str, str], *, vscode_env: bool = False
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    seen: set[str] = set()

    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if any(stale in raw_line for stale in STALE_SUBSTRINGS):
                continue
            if "=" not in raw_line:
                lines.append(raw_line)
                continue
            key = raw_line.split("=", 1)[0].strip()
            if _should_drop_env_key(key, vscode_env=vscode_env):
                continue
            if key in updates:
                lines.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
            lines.append(raw_line)
            seen.add(key)

    for key, value in updates.items():
        if key not in seen and value and not _should_drop_env_key(key, vscode_env=vscode_env):
            lines.append(f"{key}={value}")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _upsert_vscode_env(updates: dict[str, str]) -> None:
    _upsert_env_file(VSCODE_ENV_FILE, updates, vscode_env=True)


def _sql_warehouse_id(env: dict[str, str]) -> str:
    return env.get("DATABRICKS_WAREHOUSE_ID", "").strip()


def _bundle_var_overrides(
    env: dict[str, str],
    *,
    target: str = DEFAULT_BUNDLE_TARGET,
) -> dict[str, str]:
    overrides: dict[str, str] = {}
    email = _notify_email(env)
    warehouse_id = _sql_warehouse_id(env)
    if email:
        overrides["notify_email"] = email
    if warehouse_id:
        overrides["sql_warehouse_id"] = warehouse_id
    overrides.update(_genie_space_ids(env, target=target, profile=_profile(env)))
    return overrides


def _sync_bundle_var_overrides(
    env: dict[str, str],
    *,
    target: str = DEFAULT_BUNDLE_TARGET,
) -> None:
    path = _bundle_var_overrides_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)

    overrides = _bundle_var_overrides(env, target=target)

    if overrides:
        path.write_text(json.dumps(overrides, indent=2) + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()


def _sync_vscode_bundlevars(
    env: dict[str, str],
    *,
    target: str = DEFAULT_BUNDLE_TARGET,
) -> None:
    """Mirror bundle variable overrides for the VS Code extension Variables view."""
    path = _vscode_bundlevars_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)

    overrides = _bundle_var_overrides(env, target=target)

    if overrides:
        path.write_text(json.dumps(overrides, indent=2) + "\n", encoding="utf-8")
    elif path.exists():
        path.unlink()


def _vscode_bundlevars_path(target: str = DEFAULT_BUNDLE_TARGET) -> Path:
    return REPO_ROOT / ".databricks" / "bundle" / target / "vscode.bundlevars.json"


def _vscode_overrides_path(target: str = DEFAULT_BUNDLE_TARGET) -> Path:
    return REPO_ROOT / ".databricks" / "bundle" / target / "vscode.overrides.json"


def _sync_vscode_overrides(profile: str, target: str = DEFAULT_BUNDLE_TARGET) -> None:
    """Persist serverless Connect settings for the Databricks VS Code extension."""
    path = _vscode_overrides_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)

    overrides: dict[str, object] = {
        "serverless": True,
        "useClusterOverride": False,
    }
    if profile:
        overrides["profile"] = profile

    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                overrides = {**existing, **overrides}
        except json.JSONDecodeError:
            pass

    path.write_text(json.dumps(overrides, indent=2) + "\n", encoding="utf-8")


def sync_from_env_file(env_path: Path = ENV_FILE) -> None:
    file_env = _parse_env_file(env_path)
    merged = {**file_env}
    for key, value in os.environ.items():
        if value.strip():
            merged.setdefault(key, value.strip())

    email = _notify_email(merged)
    profile = _profile(merged)

    host = _workspace_host(profile)

    connect_updates: dict[str, str] = {
        "DATABRICKS_SERVERLESS_COMPUTE_ID": "auto",
    }
    if profile:
        connect_updates["DATABRICKS_CONFIG_PROFILE"] = profile
        connect_updates["databricks_profile"] = profile
    if host:
        connect_updates["DATABRICKS_HOST"] = host

    vscode_updates: dict[str, str] = {
        **connect_updates,
        "DATABRICKS_BUNDLE_TARGET": DEFAULT_BUNDLE_TARGET,
    }
    if email:
        vscode_updates["DATABRICKS_EMAIL_ACCOUNT"] = email
        vscode_updates["BUNDLE_VAR_notify_email"] = email

    _upsert_env_file(ENV_FILE, connect_updates)
    _upsert_vscode_env(vscode_updates)
    _sync_databricks_yml_workspace(host, profile)
    _sync_vscode_overrides(profile)
    _sync_bundle_var_overrides(merged)
    _sync_vscode_bundlevars(merged)

    if profile:
        print(f"Synced profile={profile!r}, serverless compute")
    else:
        print("No DATABRICKS_CONFIG_PROFILE set in .env")
    warehouse_id = _sql_warehouse_id(merged)
    if email:
        print(f"Synced notify_email={email}")
    else:
        print("No DATABRICKS_EMAIL_ACCOUNT set in .env")
    if warehouse_id:
        print(f"Synced sql_warehouse_id for Genie + SQL deploy scripts")
    else:
        print("No DATABRICKS_WAREHOUSE_ID set in .env")
    genie_ids = _genie_space_ids(merged, profile=profile)
    if genie_ids:
        print(
            "Synced Genie space IDs for nfl_copilot: "
            + ", ".join(f"{k}={v[:8]}..." for k, v in genie_ids.items())
        )
    if host:
        print(f"Synced workspace host={host.rstrip('/')}")
    print(f"Updated {ENV_FILE}")
    print(f"Updated {VSCODE_ENV_FILE}")
    if host and BUNDLE_FILE.exists():
        print(f"Updated {BUNDLE_FILE}")
    print(f"Updated {_vscode_overrides_path()}")
    if email or warehouse_id:
        print(f"Updated {_bundle_var_overrides_path()}")
        print(f"Updated {_vscode_bundlevars_path()}")


def main() -> None:
    if not ENV_FILE.exists():
        raise SystemExit(
            f"Missing {ENV_FILE}. Copy .env.example to .env and fill in your values."
        )
    sync_from_env_file()


if __name__ == "__main__":
    main()