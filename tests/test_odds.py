import pandas as pd

from nfl_predictions.odds import (
    build_odds_from_schedule,
    compute_odds_match_rate,
    compute_season_match_rates,
    extract_game_odds,
    extract_odds_lines,
    find_odds_ingest_gaps,
)


def _sample_schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "game_id": ["2024_01_A_B", "2024_01_C_D", "2024_00_X_Y", "2025_19_E_F"],
            "season": [2024, 2024, 2024, 2025],
            "week": [1, 1, 0, 19],
            "game_type": ["REG", "REG", "PRE", "WC"],
            "gameday": ["2024-09-08", "2024-09-08", "2024-08-10", "2025-01-11"],
            "home_team": ["B", "D", "X", "F"],
            "away_team": ["A", "C", "Y", "E"],
            "spread_line": [-3.5, None, -1.0, -2.5],
            "total_line": [44.5, 41.0, 35.0, 47.0],
            "away_moneyline": [150, None, 110, 120],
            "home_moneyline": [-170, -110, -130, -140],
            "away_spread_odds": [-110, None, -110, -108],
            "home_spread_odds": [-110, -110, -110, -112],
            "under_odds": [-110, -105, -110, -110],
            "over_odds": [-110, -115, -110, -110],
        }
    )


def test_extract_game_odds_excludes_preseason_and_partial_rows():
    result = extract_game_odds(_sample_schedule())

    assert set(result["game_id"]) == {"2024_01_A_B", "2025_19_E_F"}
    assert "PRE" not in result["game_type"].values
    assert result.loc[result["game_id"] == "2024_01_A_B", "spread_line"].iloc[0] == -3.5


def test_extract_odds_lines_long_format():
    game_odds = extract_game_odds(_sample_schedule())
    lines = extract_odds_lines(game_odds)

    assert set(lines["market"]) == {"spread", "total", "moneyline"}
    assert len(lines[lines["game_id"] == "2024_01_A_B"]) == 6
    away_spread = lines[
        (lines["game_id"] == "2024_01_A_B") & (lines["market"] == "spread") & (lines["side"] == "away")
    ]
    assert away_spread.iloc[0]["line"] == 3.5


def test_find_odds_ingest_gaps_flags_missing_lines():
    gaps = find_odds_ingest_gaps(_sample_schedule())

    assert set(gaps["game_id"]) == {"2024_01_C_D"}
    assert gaps.iloc[0]["gap_reason"] == "partial_odds"


def test_compute_odds_match_rate():
    schedule = _sample_schedule()
    game_odds = extract_game_odds(schedule)

    rate = compute_odds_match_rate(schedule, game_odds)
    assert rate == 2 / 3

    rates = compute_season_match_rates(schedule, game_odds, seasons=[2024, 2025])
    assert rates[2024] == 0.5
    assert rates[2025] == 1.0


def test_build_odds_from_schedule_returns_all_tables():
    game_odds, odds_lines, latest, gaps = build_odds_from_schedule(_sample_schedule())

    assert len(game_odds) == 2
    assert len(odds_lines) == 12  # 6 markets x 2 complete games
    assert len(latest) == len(game_odds)
    assert len(gaps) == 1


def test_extract_game_odds_dedupes_duplicate_schedule_rows():
    schedule = pd.concat([_sample_schedule(), _sample_schedule()], ignore_index=True)
    result = extract_game_odds(schedule)

    assert len(result) == 2
    assert result["game_id"].is_unique