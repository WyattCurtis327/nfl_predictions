import importlib.util
from pathlib import Path

import pandas as pd

_QUERIES_PATH = Path(__file__).resolve().parents[1] / "app" / "rca_dashboard" / "team_ratings_queries.py"
_spec = importlib.util.spec_from_file_location("team_ratings_queries_mod", _QUERIES_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

add_net_ratings = _mod.add_net_ratings
pbp_season_weeks_sql = _mod.pbp_season_weeks_sql
team_scoring_sql = _mod.team_scoring_sql


def test_team_scoring_sql_filters_season_and_weeks():
    sql = team_scoring_sql(
        "nfl.pbp.play_by_play",
        season=2025,
        weeks=[1, 2, 5],
    )
    assert "season = 2025" in sql
    assert "week IN (1, 2, 5)" in sql
    assert "GROUP BY team" in sql


def test_pbp_season_weeks_sql_includes_reg_season_types():
    sql = pbp_season_weeks_sql("nfl.pbp.play_by_play")
    assert "season_type IN ('REG'" in sql


def test_add_net_ratings_centers_league_averages_at_zero():
    frame = pd.DataFrame(
        [
            {"team": "KC", "games": 2, "points_for_mean": 28.0, "points_against_mean": 20.0},
            {"team": "NE", "games": 2, "points_for_mean": 20.0, "points_against_mean": 28.0},
        ]
    )
    rated = add_net_ratings(frame)
    assert round(float(rated["net_offensive"].mean()), 2) == 0.0
    assert round(float(rated["net_defensive"].mean()), 2) == 0.0
    kc = rated[rated["team"] == "KC"].iloc[0]
    assert kc["net_offensive"] > 0
    assert kc["net_defensive"] > 0