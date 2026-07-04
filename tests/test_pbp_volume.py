from pathlib import Path

import pandas as pd

from nfl_predictions.pbp_volume import (
    local_pbp_parquet_path,
    pbp_parquet_path,
)


def test_pbp_parquet_path():
    assert pbp_parquet_path("/Volumes/nfl/pbp/raw", 2025) == (
        "/Volumes/nfl/pbp/raw/play_by_play_2025.parquet"
    )
    assert pbp_parquet_path("/Volumes/nfl/pbp/raw/", 2024) == (
        "/Volumes/nfl/pbp/raw/play_by_play_2024.parquet"
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