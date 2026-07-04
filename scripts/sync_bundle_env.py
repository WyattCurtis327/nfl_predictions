"""Sync .env values into VS Code bundle env for Databricks deploy."""

from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env"
VSCODE_ENV_FILE = REPO_ROOT / ".databricks" / ".databricks.env"
STALE_SUBSTRINGS = ("BUNDLE_VAR_failure_notifications",)


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


def _upsert_vscode_env(updates: dict[str, str]) -> None:
    VSCODE_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    seen: set[str] = set()

    if VSCODE_ENV_FILE.exists():
        for raw_line in VSCODE_ENV_FILE.read_text(encoding="utf-8").splitlines():
            if any(stale in raw_line for stale in STALE_SUBSTRINGS):
                continue
            if "=" not in raw_line:
                lines.append(raw_line)
                continue
            key = raw_line.split("=", 1)[0].strip()
            if key in updates:
                lines.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
            lines.append(raw_line)
            seen.add(key)

    for key, value in updates.items():
        if key not in seen and value:
            lines.append(f"{key}={value}")

    VSCODE_ENV_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def sync_from_env_file(env_path: Path = ENV_FILE) -> None:
    file_env = _parse_env_file(env_path)
    merged = {**file_env}
    for key, value in os.environ.items():
        if value.strip():
            merged.setdefault(key, value.strip())

    email = _notify_email(merged)
    profile = _profile(merged)

    vscode_updates: dict[str, str] = {}
    if profile:
        vscode_updates["DATABRICKS_CONFIG_PROFILE"] = profile
        vscode_updates["databricks_profile"] = profile
    if email:
        vscode_updates["DATABRICKS_EMAIL_ACCOUNT"] = email
        vscode_updates["BUNDLE_VAR_notify_email"] = email

    _upsert_vscode_env(vscode_updates)

    if email:
        print(f"Synced notify_email={email}")
    else:
        print("No DATABRICKS_EMAIL_ACCOUNT set in .env")
    print(f"Updated {VSCODE_ENV_FILE}")


def main() -> None:
    if not ENV_FILE.exists():
        raise SystemExit(
            f"Missing {ENV_FILE}. Copy .env.example to .env and fill in your values."
        )
    sync_from_env_file()


if __name__ == "__main__":
    main()