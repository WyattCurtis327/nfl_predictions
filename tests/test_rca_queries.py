import importlib.util
from pathlib import Path

_QUERIES_PATH = Path(__file__).resolve().parents[1] / "app" / "weekly_picks" / "rca_queries.py"
_spec = importlib.util.spec_from_file_location("weekly_picks_rca_queries_mod", _QUERIES_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

cause_summary_sql = _mod.cause_summary_sql
list_rca_season_weeks_sql = _mod.list_rca_season_weeks_sql
missed_picks_sql = _mod.missed_picks_sql
parse_causes = _mod.parse_causes


def test_list_rca_season_weeks_sql():
    sql = list_rca_season_weeks_sql("nfl.predictions.pick_miss_rca")
    assert "FROM nfl.predictions.pick_miss_rca" in sql


def test_missed_picks_sql_filters_week():
    sql = missed_picks_sql("nfl.predictions.pick_miss_rca", season=2025, week=7)
    assert "season = 2025" in sql
    assert "week = 7" in sql
    assert "primary_cause" in sql


def test_cause_summary_sql():
    sql = cause_summary_sql("nfl.predictions.pick_miss_rca", season=2025)
    assert "GROUP BY primary_cause" in sql


def test_parse_causes_handles_json_string():
    causes = parse_causes('[{"label": "turnover_variance", "detail": "x"}]')
    assert causes[0]["label"] == "turnover_variance"