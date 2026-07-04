import pandas as pd

from nfl_predictions.nfelo import (
    apply_nfelo_to_matchup_scores,
    blend_nfelo_margin,
    normalize_nfelo_team,
    nfelo_implied_margin,
    nfelo_ratings_lookup,
    scores_from_nfelo_spread,
    select_nfelo_ratings,
)


def test_normalize_nfelo_team_maps_legacy_codes():
    assert normalize_nfelo_team("OAK") == "LV"
    assert normalize_nfelo_team("SEA") == "SEA"


def test_nfelo_implied_margin_scales_elo_difference():
    margin = nfelo_implied_margin(1600.0, 1500.0, elo_to_margin=20.0)
    assert margin == 5.0


def test_blend_nfelo_margin_moves_toward_nfelo_view():
    home_mu, away_mu = blend_nfelo_margin(
        24.0,
        20.0,
        home_nfelo=1600.0,
        away_nfelo=1500.0,
        nfelo_blend=0.5,
        elo_to_margin=20.0,
    )
    assert home_mu > away_mu
    assert home_mu > 22.0


def test_scores_from_nfelo_spread_matches_total_and_margin():
    home_mu, away_mu = scores_from_nfelo_spread(-3.5, total_line=47.5)
    assert round(home_mu + away_mu, 1) == 47.5
    assert round(home_mu - away_mu, 1) == 3.5


def test_select_nfelo_ratings_falls_back_to_prior_season():
    ratings = pd.DataFrame(
        [
            {"team": "SEA", "season": 2025, "week": 18, "nfelo": 1731.0},
            {"team": "KC", "season": 2025, "week": 18, "nfelo": 1425.0},
        ]
    )
    selected = select_nfelo_ratings(ratings, season=2026, week=1)
    assert len(selected) == 2
    assert set(selected["team"]) == {"SEA", "KC"}


def test_apply_nfelo_prefers_game_line_when_available():
    home_mu, away_mu, home_rating, away_rating, game_line = apply_nfelo_to_matchup_scores(
        24.0,
        21.0,
        home_team="PHI",
        away_team="KC",
        nfelo_lookup={"PHI": 1570.0, "KC": 1425.0},
        nfelo_game={"nfelo_home_line_close": -6.5},
        nfelo_blend=1.0,
        total_line=45.0,
    )
    assert game_line == -6.5
    assert round(home_mu - away_mu, 1) == 6.5
    assert home_rating == 1570.0
    assert away_rating == 1425.0


def test_nfelo_ratings_lookup():
    ratings = pd.DataFrame([{"team": "SEA", "nfelo": 1731.0}])
    assert nfelo_ratings_lookup(ratings) == {"SEA": 1731.0}