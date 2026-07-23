import importlib.util
from pathlib import Path

_QUERIES_PATH = Path(__file__).resolve().parents[1] / "app" / "weekly_picks" / "queries.py"
_spec = importlib.util.spec_from_file_location("weekly_picks_queries_mod", _QUERIES_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

latest_picks_sql = _mod.latest_picks_sql
list_season_weeks_sql = _mod.list_season_weeks_sql
predictions_table = _mod.predictions_table


def test_predictions_table():
    assert predictions_table("nfl", "gold") == "nfl.gold.game_predictions"


def test_list_season_weeks_sql_references_table():
    sql = list_season_weeks_sql("nfl.gold.game_predictions")
    assert "FROM nfl.gold.game_predictions" in sql
    assert "GROUP BY season, week" in sql


def test_latest_picks_sql_dedupes_and_filters_with_model_id():
    sql = latest_picks_sql(
        "nfl.gold.game_predictions",
        season=2026,
        week=1,
        has_model_id=True,
    )
    assert "ROW_NUMBER()" in sql
    assert "season = 2026" in sql
    assert "week = 1" in sql
    assert "WHERE rn = 1" in sql
    assert "COALESCE(model_id" in sql
    assert "monte_carlo" in sql


def test_latest_picks_sql_without_model_id_column():
    sql = latest_picks_sql(
        "nfl.gold.game_predictions",
        season=2026,
        week=1,
        has_model_id=False,
    )
    assert "'monte_carlo' AS model_id" in sql
    assert "COALESCE(model_id" not in sql