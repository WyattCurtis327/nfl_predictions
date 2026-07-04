"""SQL helpers for the RCA dashboard."""

from __future__ import annotations

import json
from typing import Any


def list_rca_seasons_sql(view: str) -> str:
    return f"""
        SELECT season, COUNT(*) AS misses
        FROM {view}
        GROUP BY season
        ORDER BY season DESC
    """


def list_rca_season_weeks_sql(view: str, *, season: int) -> str:
    return f"""
        SELECT season, week, COUNT(*) AS misses
        FROM {view}
        WHERE season = {int(season)}
        GROUP BY season, week
        ORDER BY week DESC
    """


def cause_summary_sql(view: str, *, season: int) -> str:
    return f"""
        SELECT primary_cause, COUNT(*) AS misses
        FROM {view}
        WHERE season = {int(season)}
        GROUP BY primary_cause
        ORDER BY misses DESC
    """


def cause_by_week_sql(view: str, *, season: int) -> str:
    return f"""
        SELECT week, primary_cause, COUNT(*) AS misses
        FROM {view}
        WHERE season = {int(season)}
        GROUP BY week, primary_cause
        ORDER BY week, misses DESC
    """


def missed_picks_sql(
    view: str,
    *,
    season: int,
    week: int | None = None,
    primary_cause: str | None = None,
) -> str:
    filters = [f"season = {int(season)}"]
    if week is not None:
        filters.append(f"week = {int(week)}")
    if primary_cause:
        safe_cause = primary_cause.replace("'", "''")
        filters.append(f"primary_cause = '{safe_cause}'")
    where_clause = " AND ".join(filters)
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
          proj_total,
          actual_away_score,
          actual_home_score,
          actual_total,
          pbp_proj_home,
          pbp_proj_away,
          nfelo_proj_home,
          nfelo_proj_away,
          market_proj_home,
          market_proj_away,
          home_profile_pf_mean,
          home_profile_pa_mean,
          away_profile_pf_mean,
          away_profile_pa_mean,
          home_profile_games,
          away_profile_games,
          game_home_turnovers,
          game_away_turnovers,
          game_home_epa,
          game_away_epa,
          profile_source,
          projection_source,
          cause_summary,
          analyzed_at
        FROM {view}
        WHERE {where_clause}
        ORDER BY week DESC, gameday, game_id
    """


def game_detail_sql(view: str, *, game_id: str) -> str:
    safe_id = game_id.replace("'", "''")
    return f"""
        SELECT *
        FROM {view}
        WHERE game_id = '{safe_id}'
        ORDER BY analyzed_at DESC
        LIMIT 1
    """


def parse_causes(raw: Any) -> list[dict[str, Any]]:
    if raw is None or raw != raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def format_narrative(row: dict[str, Any]) -> str:
    away = row.get("away_abbr", "?")
    home = row.get("home_abbr", "?")
    lines = [
        f"{away} @ {home} (week {row.get('week')}, {row.get('season')}): "
        f"missed {row.get('miss_types', 'unknown')}; primary cause: {row.get('primary_cause', 'unknown')}."
    ]
    proj_away = row.get("proj_away_score")
    proj_home = row.get("proj_home_score")
    actual_away = row.get("actual_away_score") or row.get("actual_away")
    actual_home = row.get("actual_home_score") or row.get("actual_home")
    if proj_home is not None and actual_home is not None:
        lines.append(
            f"Projected {proj_away}–{proj_home}; actual {actual_away}–{actual_home}."
        )
    for cause in parse_causes(row.get("cause_summary"))[:3]:
        lines.append(f"- {cause.get('label')}: {cause.get('detail')}")
    return "\n".join(lines)