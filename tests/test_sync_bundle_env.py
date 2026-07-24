"""Tests for scripts/sync_bundle_env.py public-yml behavior."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "sync_bundle_env.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sync_bundle_env", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sync_bundle_env"] = mod
    spec.loader.exec_module(mod)
    return mod


def _synthetic_real_host() -> str:
    return "".join(
        ("https://dbc-", "01234567", "-", "89ab", ".cloud.databricks.com")
    )


@pytest.fixture(scope="module")
def sync_mod():
    return _load_module()


def test_public_host_matches_checker(sync_mod):
    assert "xxxxxxxx" in sync_mod.PUBLIC_HOST_PLACEHOLDER


def test_ensure_public_yml_strips_personal_host_and_profile(sync_mod, tmp_path, monkeypatch):
    personal_host = _synthetic_real_host()
    bundle = tmp_path / "databricks.yml"
    bundle.write_text(
        f"""
targets:
  prod:
    workspace:
      host: {personal_host}
      profile: my_personal_profile
      root_path: /Workspace/Users/${{workspace.current_user.userName}}/.bundle/x
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(sync_mod, "BUNDLE_FILE", bundle)
    changed = sync_mod._ensure_public_databricks_yml_workspace()
    assert changed is True
    text = bundle.read_text(encoding="utf-8")
    assert sync_mod.PUBLIC_HOST_PLACEHOLDER in text
    assert "my_personal_profile" not in text
    assert "01234567" not in text
    assert "profile:" not in text
