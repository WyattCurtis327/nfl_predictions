import pandas as pd

from nfl_predictions.validate import build_weekly_refresh_checks, failed_blocking_checks


def _schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "game_id": ["2026_01_A_B", "2026_01_C_D"],
            "season": [2026, 2026],
            "week": [1, 1],
            "game_type": ["REG", "REG"],
            "gameday": ["2026-09-10", "2026-09-13"],
            "home_team": ["B", "D"],
            "away_team": ["A", "C"],
            "home_score": [None, None],
            "away_score": [None, None],
        }
    )


def _odds() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "game_id": ["2026_01_A_B", "2026_01_C_D"],
            "season": [2026, 2026],
            "week": [1, 1],
            "bookmaker": ["draftkings", "draftkings"],
            "spread_line": [-2.5, -1.0],
            "total_line": [44.5, 47.0],
            "away_moneyline": [120, 105],
            "home_moneyline": [-140, -125],
        }
    )


def test_build_weekly_refresh_checks_passes_with_full_coverage():
    checks = build_weekly_refresh_checks(
        schedule=_schedule(),
        game_odds_latest=_odds(),
        season=2026,
        pbp_rows=0,
        roster_rows=100,
        player_rows=50,
    )

    assert failed_blocking_checks(checks) == []


def test_build_weekly_refresh_checks_flags_missing_odds():
    partial_odds = _odds().head(1)
    checks = build_weekly_refresh_checks(
        schedule=_schedule(),
        game_odds_latest=partial_odds,
        season=2026,
        pbp_rows=0,
        roster_rows=100,
        player_rows=50,
        min_match_rate=0.9,
    )

    assert "odds_next_week_match_rate" in failed_blocking_checks(checks)