"""Agent-ready helpers for missed-pick root cause analysis."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd

from nfl_predictions.prediction_rca import analyze_missed_grades, filter_missed_grades, is_missed_grade


def get_weekly_misses(
    rca: pd.DataFrame,
    *,
    season: int,
    week: int | None = None,
) -> pd.DataFrame:
    """Return RCA rows for a season and optional week."""
    if rca.empty:
        return rca
    hits = rca[rca["season"] == season]
    if week is not None:
        hits = hits[hits["week"] == week]
    sort_cols = [col for col in ("week", "gameday", "game_id") if col in hits.columns]
    if sort_cols:
        hits = hits.sort_values(sort_cols)
    return hits.reset_index(drop=True)


def get_rca_report(rca: pd.DataFrame, *, game_id: str) -> dict[str, Any] | None:
    """Return one RCA report row as a dict."""
    if rca.empty:
        return None
    hits = rca[rca["game_id"].astype(str) == str(game_id)]
    if hits.empty:
        return None
    return hits.iloc[0].to_dict()


def parse_cause_summary(report: dict[str, Any]) -> list[dict[str, Any]]:
    raw = report.get("cause_summary")
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def format_rca_narrative(report: dict[str, Any]) -> str:
    """Plain-English summary suitable for chat agents or UI tooltips."""
    away = report.get("away_abbr", "?")
    home = report.get("home_abbr", "?")
    miss_types = report.get("miss_types", "unknown")
    primary = report.get("primary_cause", "unknown")
    lines = [
        f"{away} @ {home} (week {report.get('week')}, season {report.get('season')}): "
        f"missed {miss_types}; primary cause: {primary}.",
    ]

    proj_home = report.get("market_proj_home") or report.get("proj_home_score")
    proj_away = report.get("market_proj_away") or report.get("proj_away_score")
    actual_home = report.get("actual_home") or report.get("actual_home_score")
    actual_away = report.get("actual_away") or report.get("actual_away_score")
    if proj_home is not None and actual_home is not None:
        lines.append(
            f"Projected {proj_away}–{proj_home}; actual {actual_away}–{actual_home}."
        )

    for cause in parse_cause_summary(report)[:3]:
        lines.append(f"- {cause.get('label')}: {cause.get('detail')}")

    return "\n".join(lines)


def summarize_causes(rca: pd.DataFrame, *, season: int | None = None) -> pd.DataFrame:
    """Count misses by primary_cause."""
    hits = rca
    if season is not None and not hits.empty:
        hits = hits[hits["season"] == season]
    if hits.empty or "primary_cause" not in hits.columns:
        return pd.DataFrame(columns=["primary_cause", "misses"])
    return (
        hits.groupby("primary_cause", as_index=False)
        .size()
        .rename(columns={"size": "misses"})
        .sort_values("misses", ascending=False)
        .reset_index(drop=True)
    )


def filter_unanalyzed_misses(
    grades: pd.DataFrame,
    rca: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return missed grades that do not yet have an RCA row."""
    missed = filter_missed_grades(grades)
    if missed.empty:
        return missed
    if rca is None or rca.empty or "grade_id" not in rca.columns:
        return missed
    analyzed = set(rca["grade_id"].dropna().astype(str))
    return missed[~missed["grade_id"].astype(str).isin(analyzed)].copy()


def run_rca_batch(
    grades: pd.DataFrame,
    *,
    pbp: pd.DataFrame,
    game_pbp_by_id: dict[str, pd.DataFrame] | None = None,
    nfelo_games: pd.DataFrame | None = None,
    nfelo_lookup: dict[str, float] | None = None,
    current_pbp_season: int | None = None,
) -> pd.DataFrame:
    """Analyze only missed grades (idempotent input filter left to caller)."""
    pending = filter_missed_grades(grades)
    if pending.empty:
        return pd.DataFrame()
    return analyze_missed_grades(
        pending,
        pbp=pbp,
        game_pbp_by_id=game_pbp_by_id or {},
        nfelo_games=nfelo_games,
        nfelo_lookup=nfelo_lookup,
        current_pbp_season=current_pbp_season,
    )


def describe_grade_eligibility(grade: Any) -> str:
    if is_missed_grade(grade):
        return "eligible"
    return "skipped_not_miss"