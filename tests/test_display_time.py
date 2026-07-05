import importlib.util
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

_DISPLAY_TIME_PATH = (
    Path(__file__).resolve().parents[1] / "app" / "weekly_picks" / "display_time.py"
)
_spec = importlib.util.spec_from_file_location("display_time_mod", _DISPLAY_TIME_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

format_timestamp_la = _mod.format_timestamp_la
format_timestamps_in_frame = _mod.format_timestamps_in_frame


def test_format_utc_iso_to_la():
    assert format_timestamp_la("2026-07-04T23:00:00+00:00") == "2026-07-04_16_00"


def test_format_date_only_midnight_la():
    assert format_timestamp_la("2026-09-10") == "2026-09-10_00_00"


def test_format_eastern_kickoff_to_la():
    assert format_timestamp_la("2026-09-10 20:15") == "2026-09-10_17_15"


def test_format_timestamps_in_frame():
    frame = pd.DataFrame(
        {
            "gameday": ["2026-09-10"],
            "predicted_at": ["2026-07-05T03:30:00+00:00"],
            "away_abbr": ["KC"],
        }
    )
    formatted = format_timestamps_in_frame(frame)
    assert formatted.loc[0, "gameday"] == "2026-09-10_00_00"
    assert formatted.loc[0, "predicted_at"] == "2026-07-04_20_30"
    assert formatted.loc[0, "away_abbr"] == "KC"


def test_format_timestamp_la_handles_datetime():
    value = datetime(2026, 7, 4, 23, 0, tzinfo=ZoneInfo("UTC"))
    assert format_timestamp_la(value) == "2026-07-04_16_00"