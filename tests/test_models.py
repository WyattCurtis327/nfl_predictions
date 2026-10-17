import pandas as pd

from nfl_predictions.models import MODEL_IDS, ModelRunContext, run_all_models, run_model
from nfl_predictions.models.common import ModelConfig
from nfl_predictions.models.elo import compute_elo_ratings
from nfl_predictions.models.epa import compute_team_epa_profiles
from nfl_predictions.models.ensemble import blend_model_predictions
from nfl_predictions.models.poisson import predict_poisson_week
from nfl_predictions.models.shrinkage import shrink_team_profiles as shrink_profiles
from nfl_predictions.simulation import compute_team_scoring_profiles, prepare_prediction_log


def _sample_pbp() -> pd.DataFrame:
    rows = []
    games = [
        ("2025_01_KC_PHI", "PHI", "KC", 24, 21),
        ("2025_02_PHI_DAL", "DAL", "PHI", 17, 27),
        ("2025_03_KC_BUF", "BUF", "KC", 20, 24),
    ]
    for game_id, home, away, home_score, away_score in games:
        rows.append(
            {
                "game_id": game_id,
                "season": 2025,
                "week": 1,
                "gameday": "2025-09-07",
                "home_team": home,
                "away_team": away,
                "total_home_score": home_score,
                "total_away_score": away_score,
                "posteam": home,
                "defteam": away,
                "epa": 0.05,
                "play_type": "pass",
            }
        )
        rows.append(
            {
                "game_id": game_id,
                "season": 2025,
                "week": 1,
                "gameday": "2025-09-07",
                "home_team": home,
                "away_team": away,
                "total_home_score": home_score,
                "total_away_score": away_score,
                "posteam": away,
                "defteam": home,
                "epa": -0.02,
                "play_type": "run",
            }
        )
    return pd.DataFrame(rows)


def _sample_odds() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": "2026_01_KC_PHI",
                "week": 1,
                "home_abbr": "PHI",
                "away_abbr": "KC",
                "home_spread": -3.5,
                "away_spread": 3.5,
                "total_line": 47.5,
                "bookmaker": "draftkings",
            }
        ]
    )


def test_model_ids_include_core_families():
    assert "monte_carlo" in MODEL_IDS
    assert "ensemble" in MODEL_IDS
    assert "poisson" in MODEL_IDS


def test_compute_elo_ratings_orders_games():
    ratings = compute_elo_ratings(_sample_pbp())
    assert set(ratings["team"]) >= {"PHI", "KC", "DAL", "BUF"}
    assert ratings["elo"].between(1200, 1800).all()


def test_compute_team_epa_profiles():
    profiles = compute_team_epa_profiles(_sample_pbp())
    assert "net_epa" in profiles.columns
    assert len(profiles) >= 4


def test_shrink_team_profiles_pulls_toward_league_mean():
    profiles = compute_team_scoring_profiles(_sample_pbp())
    shrunk = shrink_profiles(profiles, prior_games=4.0)
    phi = profiles[profiles["team"] == "PHI"].iloc[0]
    shrunk_phi = shrunk[shrunk["team"] == "PHI"].iloc[0]
    assert abs(shrunk_phi["points_for_mean"] - phi["points_for_mean"]) < phi["points_for_mean"]


def test_poisson_week_returns_pick_row():
    profiles = compute_team_scoring_profiles(_sample_pbp())
    picks = predict_poisson_week(_sample_odds(), profiles, week=1)
    assert len(picks) == 1
    assert picks.iloc[0]["model_id"] == "poisson"
    assert picks.iloc[0]["spread_pick"] in {"PHI", "KC"}
    assert 0.0 <= picks.iloc[0]["spread_confidence"] <= 1.0


def test_run_all_models_returns_multiple_model_ids():
    pbp = _sample_pbp()
    profiles = compute_team_scoring_profiles(pbp)
    ctx = ModelRunContext(
        odds_games=_sample_odds(),
        profiles=profiles,
        week=1,
        pbp=pbp,
        training_odds=_sample_odds(),
        config=ModelConfig(),
    )
    picks = run_all_models(
        ctx,
        model_ids=("poisson", "elo", "shrinkage_profile"),
    )
    assert set(picks["model_id"]) == {"poisson", "elo", "shrinkage_profile"}


def test_ensemble_blends_model_outputs():
    profiles = compute_team_scoring_profiles(_sample_pbp())
    poisson = predict_poisson_week(_sample_odds(), profiles, week=1)
    elo = run_model(
        "elo",
        ModelRunContext(
            odds_games=_sample_odds(),
            profiles=profiles,
            week=1,
            pbp=_sample_pbp(),
        ),
    )
    blended = blend_model_predictions(
        {"poisson": poisson, "elo": elo},
        profiles=profiles,
    )
    assert len(blended) == 1
    assert blended.iloc[0]["model_id"] == "ensemble"
    assert blended.iloc[0]["ensemble_models"]


def test_prepare_prediction_log_includes_model_id_in_prediction_id():
    profiles = compute_team_scoring_profiles(_sample_pbp())
    picks = predict_poisson_week(_sample_odds(), profiles, week=1)
    logged = prepare_prediction_log(
        picks,
        season=2026,
        pbp_season=2025,
        prediction_run_id="run-abc",
    )
    assert logged.iloc[0]["model_id"] == "poisson"
    assert logged.iloc[0]["prediction_id"] == "run-abc:poisson:2026_01_KC_PHI"