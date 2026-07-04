import pandas as pd

from nfl_predictions.simulation import (
    SimulationConfig,
    calibrate_expected_scores_to_market,
    compute_team_scoring_profiles,
    expected_matchup_scores,
    simulate_game_outcomes,
    simulate_weekly_picks,
)


def _sample_pbp() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": "2025_01_KC_PHI",
                "season": 2025,
                "home_team": "PHI",
                "away_team": "KC",
                "total_home_score": 24,
                "total_away_score": 21,
            },
            {
                "game_id": "2025_02_PHI_DAL",
                "season": 2025,
                "home_team": "DAL",
                "away_team": "PHI",
                "total_home_score": 17,
                "total_away_score": 27,
            },
        ]
    )


def test_compute_team_scoring_profiles_from_pbp():
    profiles = compute_team_scoring_profiles(_sample_pbp())
    assert set(profiles["team"]) == {"PHI", "KC", "DAL"}
    phi = profiles[profiles["team"] == "PHI"].iloc[0]
    assert phi["games"] == 2
    assert phi["points_for_mean"] > 0


def test_calibrate_expected_scores_blends_market():
    home_mu, away_mu = calibrate_expected_scores_to_market(
        24.0,
        20.0,
        home_spread=-3.5,
        total_line=47.5,
        market_blend=0.5,
    )
    assert 20.0 < home_mu < 27.0
    assert 18.0 < away_mu < 24.0


def test_simulate_game_outcomes_is_deterministic_with_seed():
    cfg = SimulationConfig(random_seed=42, n_simulations=5000)
    first = simulate_game_outcomes(
        24.0,
        21.0,
        8.0,
        7.0,
        home_spread=-3.5,
        away_spread=3.5,
        total_line=45.5,
        config=cfg,
    )
    second = simulate_game_outcomes(
        24.0,
        21.0,
        8.0,
        7.0,
        home_spread=-3.5,
        away_spread=3.5,
        total_line=45.5,
        config=cfg,
    )
    assert first["home_cover_pct"] == second["home_cover_pct"]
    assert first["over_pct"] == second["over_pct"]


def test_simulate_weekly_picks_returns_recommendations():
    profiles = compute_team_scoring_profiles(_sample_pbp())
    odds = pd.DataFrame(
        [
            {
                "game_id": "2026_01_KC_PHI",
                "week": 1,
                "home_abbr": "PHI",
                "away_abbr": "KC",
                "home_spread": -3.5,
                "away_spread": 3.5,
                "total_line": 47.5,
            }
        ]
    )
    schedule = pd.DataFrame(
        [
            {
                "game_id": "2026_01_KC_PHI",
                "week": 1,
                "home_score": None,
                "away_score": None,
            }
        ]
    )
    picks = simulate_weekly_picks(
        odds,
        profiles,
        week=1,
        schedule=schedule,
        config=SimulationConfig(random_seed=7, n_simulations=2000),
    )
    assert len(picks) == 1
    assert picks.iloc[0]["spread_pick"] in {"PHI", "KC"}
    assert picks.iloc[0]["total_pick"] in {"OVER", "UNDER"}


def test_expected_matchup_scores_uses_profiles():
    profiles = compute_team_scoring_profiles(_sample_pbp())
    home_mu, away_mu, home_std, away_std = expected_matchup_scores("PHI", "KC", profiles)
    assert home_mu > away_mu
    assert home_std >= 6.0
    assert away_std >= 6.0