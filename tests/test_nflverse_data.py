import pandas as pd

from nfl_predictions.nflverse_data import (
    GAME_TYPES_REG_PLAYOFF,
    fetch_play_by_play,
    fetch_rosters,
    fetch_season_schedule,
    merge_schedule_season,
    parse_season_list,
)


def test_parse_season_list():
    assert parse_season_list("2024,2025,2026") == [2024, 2025, 2026]
    assert parse_season_list(" 2024 , 2025 ") == [2024, 2025]


def test_fetch_play_by_play_drops_preseason(monkeypatch):
    sample = pd.DataFrame(
        {
            "season": [2025, 2025, 2025],
            "season_type": ["REG", "POST", "PRE"],
            "game_id": ["g1", "g2", "g3"],
            "play_id": [1, 2, 3],
        }
    )
    monkeypatch.setattr(
        "nfl_predictions.nflverse_data.pd.read_parquet",
        lambda *_args, **_kwargs: sample,
    )

    result = fetch_play_by_play(2025)
    assert "PRE" not in result["season_type"].values
    assert len(result) == 2

    reg_only = fetch_play_by_play(2025, regular_season_only=True)
    assert set(reg_only["season_type"]) == {"REG"}


def test_fetch_rosters(monkeypatch):
    sample = pd.DataFrame(
        {
            "season": [2026, 2026],
            "team": ["SEA", "NE"],
            "full_name": ["Player A", "Player B"],
        }
    )
    monkeypatch.setattr(
        "nfl_predictions.nflverse_data.pd.read_csv",
        lambda *_args, **_kwargs: sample,
    )

    result = fetch_rosters(2026)
    assert len(result) == 2


def test_fetch_season_schedule_filters_reg_only(monkeypatch):
    sample = pd.DataFrame(
        {
            "season": [2026, 2026, 2026],
            "game_type": ["REG", "REG", "PRE"],
            "game_id": ["2026_01_NE_SEA", "2026_01_SF_LA", "2026_00_X_Y"],
            "week": [1, 1, 0],
        }
    )
    monkeypatch.setattr(
        "nfl_predictions.nflverse_data.pd.read_csv",
        lambda *_args, **_kwargs: sample,
    )

    result = fetch_season_schedule(2026, game_types=("REG",))
    assert len(result) == 2
    assert set(result["game_type"]) == {"REG"}


def test_fetch_season_schedule_includes_playoff_game_types(monkeypatch):
    sample = pd.DataFrame(
        {
            "season": [2025, 2025, 2025, 2025, 2025, 2025],
            "game_type": ["REG", "WC", "DIV", "CON", "SB", "PRE"],
            "game_id": ["g1", "g2", "g3", "g4", "g5", "g6"],
            "week": [1, 19, 20, 21, 22, 0],
        }
    )
    monkeypatch.setattr(
        "nfl_predictions.nflverse_data.pd.read_csv",
        lambda *_args, **_kwargs: sample,
    )

    result = fetch_season_schedule(2025, game_types=GAME_TYPES_REG_PLAYOFF)
    assert set(result["game_type"]) == {"REG", "WC", "DIV", "CON", "SB"}
    assert len(result) == 5


def test_merge_schedule_season_preserves_other_seasons():
    existing = pd.DataFrame(
        {
            "season": [2025, 2026],
            "game_id": ["2025_01_A_B", "2026_01_C_D"],
            "home_score": [10.0, None],
        }
    )
    refreshed = pd.DataFrame(
        {
            "season": [2026, 2026],
            "game_id": ["2026_01_C_D", "2026_01_E_F"],
            "home_score": [None, None],
        }
    )

    merged = merge_schedule_season(existing, refreshed, season=2026)
    assert len(merged) == 3
    assert set(merged["season"]) == {2025, 2026}
    assert merged.loc[merged["game_id"] == "2025_01_A_B", "home_score"].iloc[0] == 10.0


def test_merge_schedule_season_replaces_target_season_and_dedupes():
    existing = pd.DataFrame(
        {
            "season": [2026, 2026],
            "game_id": ["2026_01_C_D", "2026_01_OLD"],
            "home_score": [3.0, 7.0],
        }
    )
    refreshed = pd.DataFrame(
        {
            "season": [2026, 2026],
            "game_id": ["2026_01_C_D", "2026_01_C_D"],
            "home_score": [21.0, 99.0],
        }
    )

    merged = merge_schedule_season(existing, refreshed, season=2026)
    assert len(merged) == 1
    assert merged.iloc[0]["game_id"] == "2026_01_C_D"
    assert merged.iloc[0]["home_score"] == 99.0