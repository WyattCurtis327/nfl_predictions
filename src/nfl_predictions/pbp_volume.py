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


def is_missing_volume_path_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "path does not exist",
            "path_not_found",
            "cannot find",
            "not found",
            "no such file",
            "doesn't exist",
        )
    )


def read_volume_parquet(spark, path: str):
    """Read parquet from a UC Volume path.

    ``dbutils.fs.exists`` is unavailable in some serverless job environments,
    so existence is inferred from the Spark read attempt.
    """
    try:
        df = spark.read.parquet(path)
        df.limit(1).count()
        return df
    except Exception as exc:
        if is_missing_volume_path_error(exc):
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
    skip_unavailable: bool = False,
) -> tuple[list[dict[str, object]], list[int]]:
    """Download multiple seasons to a UC Volume.

    Returns written file metadata and seasons skipped because nflverse has not
    published PBP yet (only when ``skip_unavailable`` is True).
    """
    results: list[dict[str, object]] = []
    skipped: list[int] = []

    for season in seasons:
        try:
            dest = download_pbp_season_to_volume(
                season,
                volume,
                regular_season_only=regular_season_only,
            )
        except PbpNotAvailableError:
            if not skip_unavailable:
                raise
            skipped.append(season)
            continue

        results.append(
            {
                "season": season,
                "path": dest,
                "source": NFLVERSE_PBP_URL.format(season=season),
            }
        )

    return results, skipped


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