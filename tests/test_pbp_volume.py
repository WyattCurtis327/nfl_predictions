from pathlib import Path

import pandas as pd

from nfl_predictions.nflverse_data import PbpNotAvailableError
from nfl_predictions.pbp_volume import (
    download_pbp_seasons_to_volume,
    is_missing_volume_path_error,
    local_pbp_parquet_path,
    pbp_parquet_path,
)


def test_is_missing_volume_path_error():
    assert is_missing_volume_path_error(
        Exception(
            "[PATH_NOT_FOUND] Path does not exist: "
            "dbfs:/Volumes/nfl/landing/raw/play_by_play_2026.parquet"
        )
    )


def test_pbp_parquet_path():
    assert pbp_parquet_path("/Volumes/nfl/landing/raw", 2025) == (
        "/Volumes/nfl/landing/raw/play_by_play_2025.parquet"
    )
    assert pbp_parquet_path("/Volumes/nfl/landing/raw/", 2024) == (
        "/Volumes/nfl/landing/raw/play_by_play_2024.parquet"
    )


def test_download_pbp_season_local(monkeypatch, tmp_path: Path):
    sample = pd.DataFrame(
        {
            "season": [2024, 2024],
            "season_type": ["REG", "REG"],
            "game_id": ["g1", "g2"],
            "week": [1, 1],
        }
    )
    monkeypatch.setattr(
        "nfl_predictions.pbp_volume.fetch_play_by_play",
        lambda *_args, **_kwargs: sample,
    )

    from nfl_predictions.pbp_volume import download_pbp_season_local

    path = download_pbp_season_local(2024, tmp_path)
    assert path == local_pbp_parquet_path(tmp_path, 2024)
    assert path.exists()
    loaded = pd.read_parquet(path)
    assert len(loaded) == 2


def test_download_pbp_seasons_to_volume_skips_unavailable(monkeypatch, tmp_path: Path):
    sample = pd.DataFrame({"season": [2025], "game_id": ["g1"], "week": [1]})

    def fake_fetch(season: int, **_kwargs):
        if season == 2026:
            raise PbpNotAvailableError("missing")
        return sample

    monkeypatch.setattr("nfl_predictions.pbp_volume.fetch_play_by_play", fake_fetch)

    results, skipped = download_pbp_seasons_to_volume(
        [2025, 2026],
        str(tmp_path),
        skip_unavailable=True,
    )

    assert len(results) == 1
    assert results[0]["season"] == 2025
    assert skipped == [2026]