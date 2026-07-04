import json

import pandas as pd

from nfl_predictions.prediction_rca import (
    analyze_missed_grades,
    analyze_missed_pick,
    filter_missed_grades,
    filter_training_pbp,
    is_missed_grade,
    new_rca_run_id,
    prepare_rca_log,
    summarize_game_pbp,
)


def _training_pbp() -> pd.DataFrame:
    rows = []
    for game_id, home, away, home_score, away_score, week in [
        ("2025_01_KC_PHI", "PHI", "KC", 24, 21, 1),
        ("2025_02_PHI_DAL", "DAL", "PHI", 17, 27, 2),
        ("2025_03_KC_DEN", "DEN", "KC", 20, 28, 3),
        ("2026_01_NE_SEA", "SEA", "NE", 24, 17, 1),
        ("2026_02_SEA_SF", "SF", "SEA", 21, 24, 2),
    ]:
        season = int(game_id.split("_")[0])
        rows.append(
            {
                "game_id": game_id,
                "season": season,
                "week": week,
                "home_team": home,
                "away_team": away,
                "total_home_score": home_score,
                "total_away_score": away_score,
            }
        )
    return pd.DataFrame(rows)


def _game_pbp(game_id: str, home: str, away: str, home_score: int, away_score: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": game_id,
                "play_id": 1,
                "home_team": home,
                "away_team": away,
                "posteam": home,
                "defteam": away,
                "epa": 0.4,
                "interception": 0,
                "fumble_lost": 0,
                "total_home_score": home_score,
                "total_away_score": away_score,
            },
            {
                "game_id": game_id,
                "play_id": 2,
                "home_team": home,
                "away_team": away,
                "posteam": away,
                "defteam": home,
                "epa": -1.2,
                "interception": 1,
                "fumble_lost": 1,
                "total_home_score": home_score,
                "total_away_score": away_score,
            },
        ]
    )


def _missed_grade() -> dict:
    return {
        "grade_id": "grade-1",
        "prediction_id": "run-1:2026_03_NE_SEA",
        "game_id": "2026_03_NE_SEA",
        "season": 2026,
        "week": 3,
        "home_abbr": "SEA",
        "away_abbr": "NE",
        "spread_pick": "NE",
        "total_pick": "OVER",
        "spread_correct": False,
        "total_correct": False,
        "spread_confidence": 0.62,
        "total_confidence": 0.58,
        "away_spread": 6.5,
        "home_spread": -6.5,
        "total_line": 44.5,
        "proj_away_score": 24.0,
        "proj_home_score": 22.0,
        "proj_total": 46.0,
        "actual_away_score": 31.0,
        "actual_home_score": 17.0,
        "actual_total": 48.0,
        "pbp_season": 2025,
        "market_blend": 0.35,
        "nfelo_blend": 0.30,
        "home_field_advantage": 2.5,
    }


def test_is_missed_grade_detects_spread_and_total_misses():
    assert is_missed_grade({"spread_correct": False, "total_correct": True}) is True
    assert is_missed_grade({"spread_correct": True, "total_correct": False}) is True
    assert is_missed_grade({"spread_correct": True, "total_correct": True}) is False
    assert is_missed_grade({"spread_correct": None, "total_correct": False}) is True


def test_filter_training_pbp_excludes_target_week_and_game():
    pbp = _training_pbp()
    window = filter_training_pbp(
        pbp,
        prior_season=2025,
        current_season=2026,
        before_week=3,
        exclude_game_ids={"2026_02_SEA_SF"},
    )
    assert "2026_03_NE_SEA" not in set(window["game_id"])
    assert "2026_02_SEA_SF" not in set(window["game_id"])
    assert "2026_01_NE_SEA" in set(window["game_id"])
    assert "2025_03_KC_DEN" in set(window["game_id"])


def test_summarize_game_pbp_counts_turnovers_and_plays():
    summary = summarize_game_pbp(
        _game_pbp("2026_03_NE_SEA", "SEA", "NE", 17, 31),
        home_team="SEA",
        away_team="NE",
    )
    assert summary["play_count"] == 2
    assert summary["home_turnovers"] == 0
    assert summary["away_turnovers"] == 2


def test_analyze_missed_pick_returns_decomposition_and_causes():
    grade = _missed_grade()
    pbp = _training_pbp()
    game_pbp = _game_pbp("2026_03_NE_SEA", "SEA", "NE", 17, 31)

    report = analyze_missed_pick(
        grade,
        pbp=pbp,
        game_pbp=game_pbp,
    )

    assert report["game_id"] == "2026_03_NE_SEA"
    assert report["miss_types"] == "spread,total"
    assert report["pbp_proj_home"] is not None
    assert report["market_proj_home"] is not None
    assert report["actual_home"] == 17.0
    assert report["actual_away"] == 31.0
    assert report["home_profile_games"] >= 1
    assert report["primary_cause"] in {
        "pbp_profile_miss",
        "nfelo_adjustment",
        "market_calibration",
        "turnover_variance",
        "low_profile_sample",
        "score_projection_error",
    }

    causes = json.loads(report["cause_summary"])
    assert isinstance(causes, list)
    assert len(causes) >= 1
    assert "label" in causes[0]
    assert "detail" in causes[0]


def test_analyze_missed_grades_skips_correct_picks():
    grades = pd.DataFrame(
        [
            {**_missed_grade()},
            {
                **_missed_grade(),
                "grade_id": "grade-2",
                "prediction_id": "run-1:2026_04_X",
                "game_id": "2026_04_X",
                "spread_correct": True,
                "total_correct": True,
            },
        ]
    )
    pbp = _training_pbp()
    reports = analyze_missed_grades(grades, pbp=pbp, game_pbp_by_id={})
    assert len(reports) == 1
    assert reports.iloc[0]["game_id"] == "2026_03_NE_SEA"


def test_prepare_rca_log_attaches_run_metadata():
    report = analyze_missed_pick(_missed_grade(), pbp=_training_pbp())
    logged = prepare_rca_log(
        pd.DataFrame([report]),
        rca_run_id="rca-run-1",
        grading_run_id="grade-run-1",
    )
    assert logged.iloc[0]["rca_run_id"] == "rca-run-1"
    assert logged.iloc[0]["grading_run_id"] == "grade-run-1"
    assert logged.iloc[0]["rca_id"]


def test_new_rca_run_id_is_unique():
    assert new_rca_run_id() != new_rca_run_id()