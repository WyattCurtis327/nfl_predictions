"""Fail if tracked files contain secrets or personal operator identity.

Run from repo root:
  python scripts/check_public_ready.py

Used by CI and optional git hooks. Scans only git-tracked paths when available.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Committed databricks.yml must use this host placeholder (both targets).
PUBLIC_HOST_PLACEHOLDER = "https://dbc-xxxxxxxx-xxxx.cloud.databricks.com"

# Paths that must never appear in the index.
FORBIDDEN_TRACKED_PATHS = frozenset(
    {
        ".env",
        "staging/odds_latest.json",
    }
)

# Filename patterns that should stay untracked when they hold secrets.
FORBIDDEN_TRACKED_GLOBS = (
    re.compile(r"^\.env\..+$"),  # .env.local, .env.prod, …
)

REAL_DBC_HOST = re.compile(
    r"https?://dbc-[0-9a-f]{8}-[0-9a-f]{4}\.cloud\.databricks\.com",
    re.IGNORECASE,
)
PLACEHOLDER_HOST = re.compile(
    r"https?://dbc-x{8}-x{4}\.cloud\.databricks\.com",
    re.IGNORECASE,
)
# Databricks PATs and common API key assignments with non-empty values.
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Databricks PAT (dapi…)", re.compile(r"\bdapi[a-zA-Z0-9]{20,}\b")),
    (
        "Hardcoded ODDS_API_KEY value",
        re.compile(r"\bODDS_API_KEY\s*=\s*['\"]?[A-Za-z0-9_\-]{8,}"),
    ),
    (
        "Hardcoded odds_api_key assignment",
        re.compile(r"\bodds_api_key\s*=\s*['\"][^'\"]{8,}['\"]"),
    ),
    (
        "Bearer token literal",
        re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    ),
)
# Windows user home only (e.g. C:\Users\alice). Do not match Databricks
# /Workspace/Users/${workspace.current_user.userName} paths.
PERSONAL_PATH = re.compile(
    r"[A-Za-z]:[\\/]+Users[\\/]+(?!YOUR_USERNAME\b|yourname\b|<you>\b)[^\\/\s\"']+",
    re.IGNORECASE,
)
# profile: lines under workspace: in bundle YAML (not generic English "profile:")
BUNDLE_PROFILE_LINE = re.compile(
    r"^([ \t]*)profile:\s*(\S+)\s*$",
    re.MULTILINE,
)

# Allowlisted substrings for profile examples in docs/apps (placeholders only).
ALLOWED_PROFILE_VALUES = frozenset(
    {
        "<your-profile>",
        "YOUR_PROFILE",
        "YOUR_DATABRICKS_PROFILE",
        '""',
        "''",
        '""',
    }
)

SKIP_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".whl",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".exe",
    ".bin",
    ".parquet",
    ".arrow",
    ".zip",
    ".gz",
    ".7z",
)


def _git_tracked_files() -> list[Path] | None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    raw = result.stdout.split(b"\0")
    paths: list[Path] = []
    for item in raw:
        if not item:
            continue
        rel = item.decode("utf-8", errors="replace").replace("\\", "/")
        paths.append(Path(rel))
    return paths


def _iter_scan_files() -> list[Path]:
    tracked = _git_tracked_files()
    if tracked is not None:
        return tracked
    # Fallback when not in a git checkout: walk common source trees.
    roots = [
        REPO_ROOT / "app",
        REPO_ROOT / "src",
        REPO_ROOT / "scripts",
        REPO_ROOT / "resources",
        REPO_ROOT / "notebooks",
        REPO_ROOT / "pipelines",
        REPO_ROOT / "tests",
        REPO_ROOT / ".github",
        REPO_ROOT / ".vscode",
    ]
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                files.append(path.relative_to(REPO_ROOT))
    for name in (
        "databricks.yml",
        "README.md",
        "SECURITY.md",
        ".env.example",
        ".gitignore",
        "pyproject.toml",
        "nfl_predictions.code-workspace",
    ):
        if (REPO_ROOT / name).is_file():
            files.append(Path(name))
    return files


def _read_text(rel: Path) -> str | None:
    path = REPO_ROOT / rel
    if not path.is_file():
        return None
    if path.suffix.lower() in SKIP_SUFFIXES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def check() -> list[str]:
    errors: list[str] = []
    files = _iter_scan_files()
    rel_set = {p.as_posix().replace("\\", "/") for p in files}

    for forbidden in FORBIDDEN_TRACKED_PATHS:
        if forbidden in rel_set:
            errors.append(f"Must not be git-tracked: {forbidden}")

    for rel in sorted(rel_set):
        base = Path(rel).name
        if base == ".env.example":
            continue
        for pattern in FORBIDDEN_TRACKED_GLOBS:
            if pattern.match(base) or pattern.match(rel):
                errors.append(f"Must not be git-tracked: {rel}")

    # databricks.yml host / profile rules
    bundle_text = _read_text(Path("databricks.yml"))
    if bundle_text is None:
        errors.append("Missing databricks.yml")
    else:
        hosts = re.findall(r"^\s*host:\s*(\S+)\s*$", bundle_text, flags=re.MULTILINE)
        if not hosts:
            errors.append("databricks.yml: expected workspace host lines")
        for host in hosts:
            if host.rstrip("/") != PUBLIC_HOST_PLACEHOLDER.rstrip("/"):
                errors.append(
                    "databricks.yml: host must be the public placeholder "
                    f"{PUBLIC_HOST_PLACEHOLDER!r}, found {host!r}"
                )
        for match in BUNDLE_PROFILE_LINE.finditer(bundle_text):
            value = match.group(2).strip().strip("'\"")
            if value and value not in ALLOWED_PROFILE_VALUES:
                errors.append(
                    "databricks.yml: do not commit workspace profile "
                    f"{value!r}; use CLI --profile / .env instead"
                )
        # Real workspace hosts anywhere in the file (defensive)
        for match in REAL_DBC_HOST.finditer(bundle_text):
            if not PLACEHOLDER_HOST.fullmatch(match.group(0)):
                errors.append(
                    f"databricks.yml: real workspace host committed: {match.group(0)}"
                )

    for rel in files:
        rel_s = rel.as_posix()
        text = _read_text(rel)
        if text is None:
            continue

        # Secret-like literals (skip this checker and docs that mention patterns)
        if rel_s in {
            "scripts/check_public_ready.py",
            "tests/test_check_public_ready.py",
            "SECURITY.md",
        }:
            pass
        else:
            for label, pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    errors.append(f"{rel_s}: possible secret ({label})")

        # Personal Windows absolute paths (workspace files, scripts)
        if PERSONAL_PATH.search(text):
            errors.append(f"{rel_s}: personal absolute path (C:/Users/…)")

        # Real Databricks workspace hosts outside placeholder
        if rel_s == "databricks.yml":
            continue
        if rel_s.endswith((".md", ".py")) and "dbc-xxxxxxxx-xxxx" in text:
            # Docs / checker mentioning the placeholder — still scan for real hosts
            pass
        for match in REAL_DBC_HOST.finditer(text):
            if PLACEHOLDER_HOST.fullmatch(match.group(0)):
                continue
            errors.append(f"{rel_s}: real workspace host: {match.group(0)}")

    return errors


def main() -> int:
    errors = check()
    if errors:
        print("Public-ready check failed:\n", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print(
            "\nFix: remove secrets/identity from tracked files, "
            "copy .env.example → .env for local values, "
            "and run python scripts/sync_bundle_env.py (writes gitignored paths only).",
            file=sys.stderr,
        )
        return 1
    print("Public-ready check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
