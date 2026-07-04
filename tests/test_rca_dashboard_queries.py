import importlib.util
from pathlib import Path

_QUERIES_PATH = Path(__file__).resolve().parents[1] / "app" / "rca_dashboard" / "queries.py"
_spec = importlib.util.spec_from_file_location("rca_dashboard_queries_mod", _QUERIES_PATH)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

cause_by_week_sql = _mod.cause_by_week_sql
format_narrative = _mod.format_narrative
game_detail_sql = _mod.game_detail_sql
list_rca_seasons_sql = _mod.list_rca_seasons_sql
missed_picks_sql = _mod.missed_picks_sql
parse_causes = _mod.parse_causes


def test_list_rca_seasons_sql():
    sql = list_rca_seasons_sql("nfl.predictions.pick_miss_rca")
    assert "GROUP BY season" in sql


def test_missed_picks_sql_supports_cause_filter():
    sql = missed_picks_sql(
        "nfl.predictions.pick_miss_rca",
        season=2025,
        week=7,
        primary_cause="pbp_profile_miss",
    )
    assert "season = 2025" in sql
    assert "week = 7" in sql
    assert "primary_cause = 'pbp_profile_miss'" in sql


def test_cause_by_week_sql():
    sql = cause_by_week_sql("nfl.predictions.pick_miss_rca", season=2025)
    assert "GROUP BY week, primary_cause" in sql


def test_game_detail_sql_escapes_quotes():
    sql = game_detail_sql("nfl.predictions.pick_miss_rca", game_id="2025_01_X")
    assert "game_id = '2025_01_X'" in sql


def test_format_narrative_includes_matchup():
    text = format_narrative(
        {
            "away_abbr": "NE",
            "home_abbr": "SEA",
            "season": 2025,
            "week": 7,
            "miss_types": "spread",
            "primary_cause": "pbp_profile_miss",
            "proj_away_score": 21,
            "proj_home_score": 24,
            "actual_away_score": 28,
            "actual_home_score": 17,
            "cause_summary": "[]",
        }
    )
    assert "NE @ SEA" in text
    assert "pbp_profile_miss" in text


def test_parse_causes_empty():
    assert parse_causes(None) == []