"""Sync .env values into VS Code bundle env for Databricks deploy."""

from __future__ import annotations

import json
import os
import re
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


def _sync_databricks_yml_host(host: str) -> None:
    """Keep workspace.host in databricks.yml aligned with the CLI profile.

    The VS Code extension parses bundle YAML directly and throws
    'Invalid host name' when workspace.host is missing.
    """
    if not host or not BUNDLE_FILE.exists():
        return

    normalized = host.rstrip("/")
    text = BUNDLE_FILE.read_text(encoding="utf-8")
    host_line = f"      host: {normalized}"

    if re.search(r"^      host: ", text, flags=re.MULTILINE):
        updated = re.sub(
            r"^      host: .*$",
            host_line,
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        updated = text.replace(
            "    workspace:\n      root_path:",
            f"    workspace:\n{host_line}\n      root_path:",
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


def _sync_bundle_var_overrides(
    email: str, target: str = DEFAULT_BUNDLE_TARGET
) -> None:
    path = _bundle_var_overrides_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)

    if email:
        path.write_text(
            json.dumps({"notify_email": email}, indent=2) + "\n",
            encoding="utf-8",
        )
    elif path.exists():
        path.unlink()


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
    _sync_databricks_yml_host(host)
    _sync_vscode_overrides(profile)
    _sync_bundle_var_overrides(email)

    if profile:
        print(f"Synced profile={profile!r}, serverless compute")
    else:
        print("No DATABRICKS_CONFIG_PROFILE set in .env")
    if email:
        print(f"Synced notify_email={email}")
    else:
        print("No DATABRICKS_EMAIL_ACCOUNT set in .env")
    if host:
        print(f"Synced workspace host={host.rstrip('/')}")
    print(f"Updated {ENV_FILE}")
    print(f"Updated {VSCODE_ENV_FILE}")
    if host and BUNDLE_FILE.exists():
        print(f"Updated {BUNDLE_FILE}")
    print(f"Updated {_vscode_overrides_path()}")
    if email:
        print(f"Updated {_bundle_var_overrides_path()}")


def main() -> None:
    if not ENV_FILE.exists():
        raise SystemExit(
            f"Missing {ENV_FILE}. Copy .env.example to .env and fill in your values."
        )
    sync_from_env_file()


if __name__ == "__main__":
    main()