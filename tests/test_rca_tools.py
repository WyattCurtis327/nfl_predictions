import json

import pandas as pd

from nfl_predictions.rca_tools import (
    filter_unanalyzed_misses,
    format_rca_narrative,
    get_rca_report,
    get_weekly_misses,
    summarize_causes,
)


def _sample_rca() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "game_id": "2025_07_NE_SEA",
                "season": 2025,
                "week": 7,
                "away_abbr": "NE",
                "home_abbr": "SEA",
                "miss_types": "spread",
                "primary_cause": "pbp_profile_miss",
                "proj_away_score": 21.0,
                "proj_home_score": 24.0,
                "actual_away_score": 28.0,
                "actual_home_score": 17.0,
                "market_proj_home": 24.0,
                "market_proj_away": 21.0,
                "actual_home": 17.0,
                "actual_away": 28.0,
                "cause_summary": json.dumps(
                    [
                        {
                            "label": "pbp_profile_miss",
                            "detail": "PBP-only margin was +3.0; actual margin was -11.0.",
                            "weight": 14.0,
                        }
                    ]
                ),
            }
        ]
    )


def test_get_weekly_misses_filters_season_week():
    rca = _sample_rca()
    assert len(get_weekly_misses(rca, season=2025, week=7)) == 1
    assert get_weekly_misses(rca, season=2025, week=8).empty


def test_get_rca_report_returns_row_dict():
    report = get_rca_report(_sample_rca(), game_id="2025_07_NE_SEA")
    assert report is not None
    assert report["primary_cause"] == "pbp_profile_miss"


def test_format_rca_narrative_includes_cause_detail():
    report = get_rca_report(_sample_rca(), game_id="2025_07_NE_SEA")
    text = format_rca_narrative(report)
    assert "pbp_profile_miss" in text
    assert "NE @ SEA" in text


def test_summarize_causes_counts_labels():
    summary = summarize_causes(_sample_rca(), season=2025)
    assert summary.iloc[0]["primary_cause"] == "pbp_profile_miss"
    assert summary.iloc[0]["misses"] == 1


def test_filter_unanalyzed_misses():
    grades = pd.DataFrame(
        [
            {"grade_id": "g1", "spread_correct": False, "total_correct": True},
            {"grade_id": "g2", "spread_correct": True, "total_correct": True},
        ]
    )
    rca = pd.DataFrame([{"grade_id": "g1"}])
    pending = filter_unanalyzed_misses(grades, rca)
    assert pending.empty

    fresh = filter_unanalyzed_misses(grades, pd.DataFrame())
    assert list(fresh["grade_id"]) == ["g1"]