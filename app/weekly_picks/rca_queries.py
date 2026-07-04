"""SQL helpers for missed picks and RCA in the weekly picks app."""

from __future__ import annotations

import json
from typing import Any


def list_rca_season_weeks_sql(view: str) -> str:
    return f"""
        SELECT season, week, COUNT(*) AS misses
        FROM {view}
        GROUP BY season, week
        ORDER BY season DESC, week DESC
    """


def missed_picks_sql(view: str, *, season: int, week: int) -> str:
    return f"""
        SELECT
          game_id,
          season,
          week,
          gameday,
          away_abbr,
          home_abbr,
          spread_pick,
          spread_confidence,
          spread_correct,
          total_pick,
          total_confidence,
          total_correct,
          miss_types,
          primary_cause,
          proj_away_score,
          proj_home_score,
          actual_away_score,
          actual_home_score,
          pbp_proj_home,
          pbp_proj_away,
          nfelo_proj_home,
          nfelo_proj_away,
          market_proj_home,
          market_proj_away,
          home_profile_pf_mean,
          away_profile_pf_mean,
          game_home_turnovers,
          game_away_turnovers,
          profile_source,
          projection_source,
          cause_summary,
          analyzed_at
        FROM {view}
        WHERE season = {int(season)}
          AND week = {int(week)}
        ORDER BY gameday, game_id
    """


def cause_summary_sql(view: str, *, season: int) -> str:
    return f"""
        SELECT primary_cause, COUNT(*) AS misses
        FROM {view}
        WHERE season = {int(season)}
        GROUP BY primary_cause
        ORDER BY misses DESC
    """


def parse_causes(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw != raw:  # NaN
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []