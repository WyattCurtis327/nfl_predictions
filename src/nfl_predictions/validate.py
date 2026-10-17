"""Validation helpers for bootstrap and weekly refresh gates."""

from __future__ import annotations

from typing import Any

import pandas as pd

from nfl_predictions.odds_api import assess_schedule_match_rate
from nfl_predictions.simulation import filter_schedule_game_types, infer_next_week


class WeeklyRefreshValidationError(RuntimeError):
    """Raised when one or more weekly refresh checks fail."""


def build_weekly_refresh_checks(
    *,
    schedule: pd.DataFrame,
    game_odds_latest: pd.DataFrame,
    season: int,
    pbp_rows: int = 0,
    roster_rows: int = 0,
    player_rows: int = 0,
    min_match_rate: float = 0.9,
    preferred_bookmaker: str = "draftkings",
) -> list[dict[str, Any]]:
    """Return weekly refresh validation rows for display and gating."""
    checks: list[dict[str, Any]] = []
    season_schedule = filter_schedule_game_types(schedule)
    season_schedule = season_schedule[season_schedule["season"] == season].copy()
    reg_games = season_schedule[season_schedule["game_type"] == "REG"]

    checks.append(
        {
            "name": "schedule_reg_games",
            "expect": "> 0 REG games for season",
            "actual": len(reg_games),
            "passed": len(reg_games) > 0,
            "blocking": True,
        }
    )

    target_week = infer_next_week(season_schedule, season=season)
    checks.append(
        {
            "name": "schedule_next_week",
            "expect": "next unplayed week identified",
            "actual": target_week,
            "passed": target_week is not None,
            "blocking": True,
        }
    )

    checks.append(
        {
            "name": "rosters_rows",
            "expect": "> 0 roster rows",
            "actual": roster_rows,
            "passed": roster_rows > 0,
            "blocking": True,
        }
    )

    checks.append(
        {
            "name": "pbp_current_season_rows",
            "expect": ">= 0 plays (0 OK before first kickoff)",
            "actual": pbp_rows,
            "passed": pbp_rows >= 0,
            "blocking": False,
        }
    )

    checks.append(
        {
            "name": "players_rows",
            "expect": "> 0 player dimension rows",
            "actual": player_rows,
            "passed": player_rows > 0,
            "blocking": True,
        }
    )

    if target_week is None:
        checks.append(
            {
                "name": "odds_next_week_match_rate",
                "expect": f">= {min_match_rate:.0%} scheduled games with live odds",
                "actual": "skipped (no target week)",
                "passed": False,
                "blocking": True,
            }
        )
        return checks

    week_schedule = season_schedule[season_schedule["week"] == target_week].copy()
    week_odds = game_odds_latest.copy()
    if preferred_bookmaker and "bookmaker" in week_odds.columns:
        preferred = week_odds[
            week_odds["bookmaker"].astype(str).str.lower() == preferred_bookmaker.lower()
        ]
        if not preferred.empty:
            week_odds = preferred

    if not week_odds.empty and "week" in week_odds.columns:
        week_odds = week_odds[week_odds["week"] == target_week]

    match_stats = assess_schedule_match_rate(
        week_schedule,
        week_odds,
        min_rate=min_match_rate,
    )
    checks.append(
        {
            "name": "odds_next_week_match_rate",
            "expect": f">= {min_match_rate:.0%} scheduled games with live odds",
            "actual": match_stats["match_rate"],
            "passed": match_stats["passed"],
            "blocking": True,
        }
    )

    duplicate_game_ids = 0
    if not week_odds.empty and "game_id" in week_odds.columns:
        duplicate_game_ids = int(week_odds["game_id"].duplicated().sum())

    checks.append(
        {
            "name": "odds_latest_no_duplicate_game_ids",
            "expect": "0 duplicate game_id rows for target week",
            "actual": duplicate_game_ids,
            "passed": duplicate_game_ids == 0,
            "blocking": True,
        }
    )

    return checks


def failed_blocking_checks(checks: list[dict[str, Any]]) -> list[str]:
    return [
        str(row["name"])
        for row in checks
        if row.get("blocking") and not row.get("passed")
    ]