import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "weekly_picks"))

from queries import latest_picks_sql, list_season_weeks_sql, predictions_table


def test_predictions_table():
    assert predictions_table("nfl", "predictions") == "nfl.predictions.game_predictions"


def test_list_season_weeks_sql_references_table():
    sql = list_season_weeks_sql("nfl.predictions.game_predictions")
    assert "FROM nfl.predictions.game_predictions" in sql
    assert "GROUP BY season, week" in sql


def test_latest_picks_sql_dedupes_and_filters():
    sql = latest_picks_sql("nfl.predictions.game_predictions", season=2026, week=1)
    assert "ROW_NUMBER()" in sql
    assert "season = 2026" in sql
    assert "week = 1" in sql
    assert "WHERE rn = 1" in sql