"""Ingest lineage metadata for Unity Catalog tables."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def stamp_dataframe(
    pdf: pd.DataFrame,
    *,
    source_file: str,
    ingested_at: datetime | None = None,
) -> pd.DataFrame:
    """Add standard ingest metadata columns."""
    frame = pdf.copy()
    frame["ingested_at"] = ingested_at or utc_now()
    frame["_source_file"] = source_file
    return frame