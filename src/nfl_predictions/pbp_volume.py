"""Play-by-play Volume download helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nfl_predictions.nflverse_data import (
    NFLVERSE_PBP_URL,
    PbpNotAvailableError,
    fetch_play_by_play,
    parse_season_list,
)


def read_volume_parquet(spark, path: str):
    """Read parquet from a UC Volume path.

    ``dbutils.fs.exists`` is unavailable in some serverless job environments,
    so existence is inferred from the Spark read attempt.
    """
    try:
        return spark.read.parquet(path)
    except Exception as exc:
        message = str(exc).lower()
        if any(
            token in message
            for token in (
                "path does not exist",
                "path_not_found",
                "cannot find",
                "not found",
                "no such file",
                "doesn't exist",
            )
        ):
            raise FileNotFoundError(f"Missing volume file: {path}") from exc
        raise


def pbp_parquet_path(volume: str, season: int) -> str:
    """Return UC Volume path for a season parquet file."""
    base = volume.rstrip("/")
    return f"{base}/play_by_play_{season}.parquet"


def download_pbp_season_to_volume(
    season: int,
    volume: str,
    *,
    regular_season_only: bool = False,
) -> str:
    """Fetch nflverse PBP and write parquet to a UC Volume path."""
    pbp = fetch_play_by_play(season, regular_season_only=regular_season_only)
    dest = pbp_parquet_path(volume, season)
    pbp.to_parquet(dest, index=False)
    return dest


def download_pbp_seasons_to_volume(
    seasons: list[int],
    volume: str,
    *,
    regular_season_only: bool = False,
) -> list[str]:
    """Download multiple seasons; raises on first unavailable season."""
    paths: list[str] = []
    for season in seasons:
        paths.append(
            download_pbp_season_to_volume(
                season,
                volume,
                regular_season_only=regular_season_only,
            )
        )
    return paths


def parse_pbp_seasons(value: str) -> list[int]:
    return parse_season_list(value)


def local_pbp_parquet_path(output_dir: str | Path, season: int) -> Path:
    return Path(output_dir) / f"play_by_play_{season}.parquet"


def download_pbp_season_local(
    season: int,
    output_dir: str | Path,
    *,
    regular_season_only: bool = False,
) -> Path:
    """Download PBP to a local directory (for offline staging)."""
    pbp = fetch_play_by_play(season, regular_season_only=regular_season_only)
    dest = local_pbp_parquet_path(output_dir, season)
    dest.parent.mkdir(parents=True, exist_ok=True)
    pbp.to_parquet(dest, index=False)
    return dest