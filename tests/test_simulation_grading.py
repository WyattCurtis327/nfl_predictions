import pandas as pd

from nfl_predictions.simulation import (
    filter_ungraded_predictions,
    grade_predictions,
    infer_latest_completed_week,
    prepare_odds_for_simulation,
    prepare_prediction_log,
    prepare_schedule_for_grading,
    resolve_spread_result,
    resolve_total_result,
    select_latest_prediction_run,
    summarize_prediction_accuracy,
)


def test_resolve_spread_and_total_results():
    assert resolve_spread_result(17, 24, away_spread=3.5, home_spread=-3.5) == "home"
    assert resolve_spread_result(21, 24, away_spread=3.5, home_spread=-3.5) == "away"
    assert resolve_total_result(45, 44.5) == "over"
    assert resolve_total_result(40, 44.5) == "under"


def test_prepare_odds_for_simulation_maps_spreads():
    odds = pd.DataFrame(
        [
            {
                "game_id": "2026_01_NE_SEA",
                "bookmaker": "draftkings",
                "home_team": "SEA",
                "away_team": "NE",
                "spread_line": -3.5,
                "total_line": 44.5,
            }
        ]
    )
    prepared = prepare_odds_for_simulation(odds, preferred_bookmaker="draftkings")
    assert prepared.iloc[0]["away_spread"] == -3.5
    assert prepared.iloc[0]["home_spread"] == 3.5
    assert prepared.iloc[0]["away_abbr"] == "NE"


def test_grade_predictions_marks_correct_picks():
    predictions = prepare_prediction_log(
        pd.DataFrame(
            [
                {
                    "game_id": "2026_01_NE_SEA",
                    "week": 1,
                    "away_abbr": "NE",
                    "home_abbr": "SEA",
                    "spread_pick": "NE",
                    "total_pick": "OVER",
                    "spread_confidence": 0.61,
                    "total_confidence": 0.58,
                    "proj_away_score": 21.0,
                    "proj_home_score": 25.0,
                    "proj_total": 46.0,
                }
            ]
        ),
        season=2026,
        pbp_season=2025,
        prediction_run_id="run-1",
    )
    schedule = prepare_schedule_for_grading(
        pd.DataFrame(
            [
                {
                    "game_id": "2026_01_NE_SEA",
                    "home_team": "SEA",
                    "away_team": "NE",
                    "home_score": 24.0,
                    "away_score": 20.0,
                    "spread_line": 3.5,
                    "total_line": 44.5,
                }
            ]
        )
    )

    graded = grade_predictions(predictions, schedule)
    assert len(graded) == 1
    assert graded.iloc[0]["spread_correct"] == False  # noqa: E712
    assert graded.iloc[0]["actual_spread_result"] == "home"
    assert graded.iloc[0]["total_correct"] == False  # noqa: E712
    assert graded.iloc[0]["actual_total_result"] == "under"

    assert graded.iloc[0]["game_type"] is None
    assert graded.iloc[0]["nfelo_blend"] == 0.30
    metrics = summarize_prediction_accuracy(graded)
    assert metrics["spread_accuracy"] == 0.0
    assert metrics["total_accuracy"] == 0.0


def test_grade_predictions_keeps_schedule_game_type():
    predictions = prepare_prediction_log(
        pd.DataFrame(
            [
                {
                    "game_id": "2025_01_NE_SEA",
                    "week": 1,
                    "game_type": "PRE",
                    "away_abbr": "NE",
                    "home_abbr": "SEA",
                    "spread_pick": "NE",
                    "total_pick": "OVER",
                }
            ]
        ),
        season=2025,
        pbp_season=2024,
        prediction_run_id="run-1",
    )
    schedule = prepare_schedule_for_grading(
        pd.DataFrame(
            [
                {
                    "game_id": "2025_01_NE_SEA",
                    "game_type": "REG",
                    "home_team": "SEA",
                    "away_team": "NE",
                    "home_score": 24.0,
                    "away_score": 20.0,
                    "spread_line": 3.5,
                    "total_line": 44.5,
                }
            ]
        )
    )
    graded = grade_predictions(predictions, schedule)
    assert graded.iloc[0]["game_type"] == "REG"


def test_select_latest_prediction_run():
    predictions = pd.DataFrame(
        [
            {
                "season": 2026,
                "week": 1,
                "prediction_run_id": "run-old",
                "predicted_at": "2026-06-01T10:00:00+00:00",
            },
            {
                "season": 2026,
                "week": 1,
                "prediction_run_id": "run-new",
                "predicted_at": "2026-06-02T10:00:00+00:00",
            },
        ]
    )
    assert select_latest_prediction_run(predictions, season=2026, week=1) == "run-new"


def test_filter_ungraded_predictions():
    predictions = pd.DataFrame(
        [
            {"prediction_id": "a", "game_id": "g1"},
            {"prediction_id": "b", "game_id": "g2"},
        ]
    )
    grades = pd.DataFrame([{"prediction_id": "a"}])
    remaining = filter_ungraded_predictions(predictions, grades)
    assert list(remaining["prediction_id"]) == ["b"]


def test_infer_latest_completed_week():
    schedule = pd.DataFrame(
        [
            {
                "season": 2026,
                "week": 1,
                "game_type": "REG",
                "home_score": 24.0,
                "away_score": 17.0,
            },
            {
                "season": 2026,
                "week": 1,
                "game_type": "REG",
                "home_score": 20.0,
                "away_score": 21.0,
            },
            {
                "season": 2026,
                "week": 2,
                "game_type": "REG",
                "home_score": None,
                "away_score": None,
            },
        ]
    )
    assert infer_latest_completed_week(schedule, season=2026) == 1