"""Tests for scripts/check_public_ready.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_public_ready.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_public_ready", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_public_ready"] = mod
    spec.loader.exec_module(mod)
    return mod


def _synthetic_real_host() -> str:
    # Built in pieces so this file does not contain a continuous real host URL.
    return "".join(
        ("https://dbc-", "01234567", "-", "89ab", ".cloud.databricks.com")
    )


@pytest.fixture(scope="module")
def check_mod():
    return _load_module()


def test_public_host_placeholder_constant(check_mod):
    assert "xxxxxxxx" in check_mod.PUBLIC_HOST_PLACEHOLDER
    assert check_mod.PUBLIC_HOST_PLACEHOLDER.startswith("https://dbc-")


def test_repo_passes_public_ready_check(check_mod):
    errors = check_mod.check()
    assert errors == [], "public-ready failures:\n" + "\n".join(errors)


def test_placeholder_host_regex_accepts_public_host(check_mod):
    host = check_mod.PUBLIC_HOST_PLACEHOLDER
    assert check_mod.PLACEHOLDER_HOST.fullmatch(host)
    assert not check_mod.PLACEHOLDER_HOST.fullmatch(_synthetic_real_host())


def test_real_dbc_host_regex(check_mod):
    real = _synthetic_real_host()
    assert check_mod.REAL_DBC_HOST.search(real)
    # Placeholder uses x's, not hex — must not look like a real workspace host.
    assert check_mod.REAL_DBC_HOST.search(check_mod.PUBLIC_HOST_PLACEHOLDER) is None
