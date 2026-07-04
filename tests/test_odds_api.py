from datetime import datetime, timezone

import pandas as pd

from nfl_predictions.odds_api import (
    assess_schedule_match_rate,
    build_odds_from_api,
    kickoff_et_date,
    match_game_ids,
    to_game_odds_rows,
)


def _schedule() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "game_id": ["2026_01_KC_PHI", "2026_01_DAL_NYG"],
            "season": [2026, 2026],
            "week": [1, 1],
            "game_type": ["REG", "REG"],
            "gameday": ["2026-09-10", "2026-09-13"],
            "home_team": ["PHI", "NYG"],
            "away_team": ["KC", "DAL"],
        }
    )


def _odds_game(
    *,
    game_id: str,
    away_team: str,
    home_team: str,
    commence_time: str,
) -> dict:
    return {
        "id": game_id,
        "away_team": away_team,
        "home_team": home_team,
        "commence_time": commence_time,
        "bookmakers": [
            {
                "key": "draftkings",
                "title": "DraftKings",
                "markets": [
                    {
                        "key": "h2h",
                        "outcomes": [
                            {"name": away_team, "price": 120},
                            {"name": home_team, "price": -140},
                        ],
                    },
                    {
                        "key": "spreads",
                        "outcomes": [
                            {"name": away_team, "point": 2.5, "price": -110},
                            {"name": home_team, "point": -2.5, "price": -110},
                        ],
                    },
                    {
                        "key": "totals",
                        "outcomes": [
                            {"name": "Over", "point": 47.5, "price": -105},
                            {"name": "Under", "point": 47.5, "price": -115},
                        ],
                    },
                ],
            }
        ],
    }


def test_kickoff_et_date_converts_utc_to_eastern():
    assert kickoff_et_date("2026-09-11T00:20:00Z") == "2026-09-10"


def test_match_game_ids_joins_on_abbr_and_gameday():
    schedule = _schedule()
    odds_games = [
        _odds_game(
            game_id="api-1",
            away_team="Kansas City Chiefs",
            home_team="Philadelphia Eagles",
            commence_time="2026-09-11T00:20:00Z",
        )
    ]

    lookup = match_game_ids(odds_games, schedule)

    assert lookup["api-1"]["game_id"] == "2026_01_KC_PHI"
    assert lookup["api-1"]["week"] == 1


def test_to_game_odds_rows_uses_nfl_predictions_schema():
    schedule = _schedule()
    ingested_at = datetime(2026, 7, 3, tzinfo=timezone.utc)
    odds_games = [
        _odds_game(
            game_id="api-1",
            away_team="Kansas City Chiefs",
            home_team="Philadelphia Eagles",
            commence_time="2026-09-11T00:20:00Z",
        )
    ]

    rows = to_game_odds_rows(
        odds_games,
        schedule,
        preferred_bookmaker="draftkings",
        ingested_at=ingested_at,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["game_id"] == "2026_01_KC_PHI"
    assert row["spread_line"] == -2.5
    assert row["total_line"] == 47.5
    assert row["bookmaker"] == "draftkings"
    assert row["source"] == "odds_api"


def test_build_odds_from_api_filters_to_target_week():
    schedule = _schedule()
    odds_games = [
        _odds_game(
            game_id="api-1",
            away_team="Kansas City Chiefs",
            home_team="Philadelphia Eagles",
            commence_time="2026-09-11T00:20:00Z",
        ),
        _odds_game(
            game_id="api-2",
            away_team="Dallas Cowboys",
            home_team="New York Giants",
            commence_time="2026-09-14T00:20:00Z",
        ),
    ]

    game_odds, odds_lines, latest, gaps = build_odds_from_api(
        odds_games,
        schedule,
        season=2026,
        week=1,
    )

    assert set(game_odds["game_id"]) == {"2026_01_KC_PHI", "2026_01_DAL_NYG"}
    assert len(odds_lines) == 12
    assert gaps.empty

    stats = assess_schedule_match_rate(schedule, game_odds, min_rate=0.9)
    assert stats["passed"] is True
    assert stats["match_rate"] == 1.0