"""Format timestamps for Streamlit apps in America/Los_Angeles."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

LA = ZoneInfo("America/Los_Angeles")
ET = ZoneInfo("America/New_York")
DISPLAY_FORMAT = "%Y-%m-%d_%H_%M"

DISPLAY_TIMESTAMP_COLUMNS: tuple[str, ...] = (
    "predicted_at",
    "analyzed_at",
    "graded_at",
    "ingested_at",
    "gameday",
    "kickoff_et",
)

_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ET_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def format_timestamp_la(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and pd.isna(value):
        return "—"
    try:
        if pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass

    if isinstance(value, pd.Timestamp):
        dt = value.to_pydatetime()
    elif isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if not text:
            return "—"
        if _DATE_ONLY.match(text):
            dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=LA)
        elif _ET_DATETIME.match(text):
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=ET)
        else:
            normalized = text.replace("Z", "+00:00")
            if " " in normalized and "T" not in normalized:
                normalized = normalized.replace(" ", "T", 1)
            dt = datetime.fromisoformat(normalized)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LA)
    return dt.astimezone(LA).strftime(DISPLAY_FORMAT)


def format_timestamps_in_frame(
    frame: pd.DataFrame,
    columns: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    cols = tuple(columns) if columns is not None else DISPLAY_TIMESTAMP_COLUMNS
    formatted = frame.copy()
    for column in cols:
        if column in formatted.columns:
            formatted[column] = formatted[column].map(format_timestamp_la)
    return formatted