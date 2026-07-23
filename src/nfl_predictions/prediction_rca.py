"""Deterministic root-cause analysis for missed NFL predictions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from nfl_predictions.nfelo import apply_nfelo_to_matchup_scores, nfelo_games_lookup
from nfl_predictions.simulation import (
    DEFAULT_HOME_FIELD_ADVANTAGE,
    DEFAULT_MARKET_BLEND,
    DEFAULT_NFELO_BLEND,
    SimulationConfig,
    calibrate_expected_scores_to_market,
    combine_pbp_seasons,
    compute_team_scoring_profiles,
    expected_matchup_scores,
)

LOW_PROFILE_GAMES_THRESHOLD = 4
HIGH_TURNOVER_THRESHOLD = 3


def new_rca_run_id() -> str:
    return str(uuid4())


def _row_get(row: Any, name: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(name, default)
    return getattr(row, name, default)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def is_missed_grade(grade: Any) -> bool:
    """Return True when spread or total pick was wrong (not push / unset)."""
    spread_correct = _row_get(grade, "spread_correct")
    total_correct = _row_get(grade, "total_correct")
    spread_miss = spread_correct is False
    total_miss = total_correct is False
    return spread_miss or total_miss


def filter_missed_grades(grades: pd.DataFrame) -> pd.DataFrame:
    if grades.empty:
        return grades
    mask = grades.apply(is_missed_grade, axis=1)
    return grades[mask].copy()


def filter_training_pbp(
    pbp: pd.DataFrame,
    *,
    prior_season: int,
    current_season: int,
    before_week: int,
    exclude_game_ids: set[str] | None = None,
) -> pd.DataFrame:
    """Rebuild the PBP window available before a target game kicks off."""
    if pbp.empty:
        return pbp

    combined = combine_pbp_seasons(
        pbp,
        pbp,
        prior_season=prior_season,
        current_season=current_season,
    )
    if combined.empty:
        return combined

    frames: list[pd.DataFrame] = []
    if "season" in combined.columns:
        prior = combined[combined["season"] == prior_season]
        if not prior.empty:
            frames.append(prior)

        current = combined[combined["season"] == current_season].copy()
        if not current.empty and "week" in current.columns:
            current = current[current["week"] < before_week]
        if not current.empty:
            frames.append(current)

    if not frames:
        return pd.DataFrame()

    window = pd.concat(frames, ignore_index=True)
    if "game_id" in window.columns:
        window = window.drop_duplicates(subset=["game_id"], keep="last")
        if exclude_game_ids:
            window = window[~window["game_id"].isin(exclude_game_ids)]
    return window.reset_index(drop=True)


def summarize_game_pbp(
    game_pbp: pd.DataFrame,
    *,
    home_team: str,
    away_team: str,
) -> dict[str, float | int | None]:
    """Aggregate play-level signals from the actual game."""
    if game_pbp.empty:
        return {
            "play_count": 0,
            "home_turnovers": None,
            "away_turnovers": None,
            "home_epa": None,
            "away_epa": None,
        }

    plays = game_pbp.copy()
    play_count = int(len(plays))

    home_turnovers = _count_turnovers(plays, team=home_team)
    away_turnovers = _count_turnovers(plays, team=away_team)
    home_epa = _team_epa(plays, team=home_team)
    away_epa = _team_epa(plays, team=away_team)

    return {
        "play_count": play_count,
        "home_turnovers": home_turnovers,
        "away_turnovers": away_turnovers,
        "home_epa": home_epa,
        "away_epa": away_epa,
    }


def _count_turnovers(plays: pd.DataFrame, *, team: str) -> int | None:
    if "posteam" not in plays.columns:
        return None

    team_plays = plays[plays["posteam"] == team]
    if team_plays.empty:
        return 0

    turnovers = 0
    for column in ("interception", "fumble_lost"):
        if column in team_plays.columns:
            turnovers += int(pd.to_numeric(team_plays[column], errors="coerce").fillna(0).sum())
    return turnovers


def _team_epa(plays: pd.DataFrame, *, team: str) -> float | None:
    if "posteam" not in plays.columns or "epa" not in plays.columns:
        return None
    team_plays = plays[plays["posteam"] == team]
    if team_plays.empty:
        return None
    return round(float(pd.to_numeric(team_plays["epa"], errors="coerce").fillna(0).sum()), 2)


def _profile_snapshot(profiles: pd.DataFrame, team: str) -> dict[str, float | int | None]:
    hit = profiles[profiles["team"] == team]
    if hit.empty:
        return {
            "games": 0,
            "points_for_mean": None,
            "points_against_mean": None,
        }
    row = hit.iloc[0]
    return {
        "games": int(row["games"]),
        "points_for_mean": _round_score(row["points_for_mean"]),
        "points_against_mean": _round_score(row["points_against_mean"]),
    }


def _profile_shift_if_game_included(
    training_pbp: pd.DataFrame,
    *,
    team: str,
    game_id: str,
    points_for: float,
    points_against: float,
) -> float | None:
    if training_pbp.empty:
        return None

    baseline = compute_team_scoring_profiles(training_pbp)
    baseline_pf = _profile_snapshot(baseline, team)["points_for_mean"]
    if baseline_pf is None:
        return None

    extra = training_pbp[training_pbp["game_id"] == game_id]
    if not extra.empty:
        augmented = training_pbp
    else:
        sample = training_pbp.iloc[0].to_dict()
        sample.update(
            {
                "game_id": game_id,
                "home_team": team,
                "away_team": "OPP",
                "total_home_score": points_for,
                "total_away_score": points_against,
            }
        )
        augmented = pd.concat([training_pbp, pd.DataFrame([sample])], ignore_index=True)

    updated = compute_team_scoring_profiles(augmented)
    updated_pf = _profile_snapshot(updated, team)["points_for_mean"]
    if updated_pf is None:
        return None
    return _round_score(updated_pf - baseline_pf)


def _miss_types(grade: Any) -> str:
    types: list[str] = []
    if _row_get(grade, "spread_correct") is False:
        types.append("spread")
    if _row_get(grade, "total_correct") is False:
        types.append("total")
    return ",".join(types)


def _projection_stages(
    *,
    home_team: str,
    away_team: str,
    profiles: pd.DataFrame,
    home_spread: float | None,
    total_line: float | None,
    config: SimulationConfig,
    game_id: str | None,
    nfelo_game: dict[str, Any] | None,
    nfelo_lookup: dict[str, float],
) -> dict[str, float]:
    home_mu, away_mu, _, _ = expected_matchup_scores(
        home_team,
        away_team,
        profiles,
        home_field_advantage=config.home_field_advantage,
    )
    pbp_home, pbp_away = home_mu, away_mu

    nfelo_home, nfelo_away, _, _, _ = apply_nfelo_to_matchup_scores(
        home_mu,
        away_mu,
        home_team=home_team,
        away_team=away_team,
        nfelo_lookup=nfelo_lookup,
        nfelo_game=nfelo_game,
        nfelo_blend=config.nfelo_blend,
        total_line=total_line,
    )
    market_home, market_away = calibrate_expected_scores_to_market(
        nfelo_home,
        nfelo_away,
        home_spread=home_spread,
        total_line=total_line,
        market_blend=config.market_blend,
    )
    return {
        "pbp_home": round(pbp_home, 2),
        "pbp_away": round(pbp_away, 2),
        "nfelo_home": round(nfelo_home, 2),
        "nfelo_away": round(nfelo_away, 2),
        "market_home": round(market_home, 2),
        "market_away": round(market_away, 2),
    }


def _rank_causes(
    *,
    grade: Any,
    stages: dict[str, float],
    actual_home: float,
    actual_away: float,
    home_profile: dict[str, float | int | None],
    away_profile: dict[str, float | int | None],
    game_summary: dict[str, float | int | None],
    home_pf_shift: float | None,
    away_pf_shift: float | None,
) -> list[dict[str, str | float]]:
    causes: list[dict[str, str | float]] = []
    actual_margin = actual_home - actual_away
    actual_total = actual_home + actual_away

    pbp_margin = stages["pbp_home"] - stages["pbp_away"]
    nfelo_margin = stages["nfelo_home"] - stages["nfelo_away"]
    market_margin = stages["market_home"] - stages["market_away"]

    pbp_total = stages["pbp_home"] + stages["pbp_away"]
    nfelo_total = stages["nfelo_home"] + stages["nfelo_away"]
    market_total = stages["market_home"] + stages["market_away"]

    proj_home = _safe_float(_row_get(grade, "proj_home_score"))
    proj_away = _safe_float(_row_get(grade, "proj_away_score"))
    final_margin = (proj_home - proj_away) if proj_home is not None and proj_away is not None else market_margin
    final_total = (proj_home + proj_away) if proj_home is not None and proj_away is not None else market_total

    spread_miss = _row_get(grade, "spread_correct") is False
    total_miss = _row_get(grade, "total_correct") is False

    if spread_miss:
        nfelo_shift = nfelo_margin - pbp_margin
        market_shift = market_margin - nfelo_margin
        causes.append(
            {
                "label": "pbp_profile_miss",
                "detail": (
                    f"PBP-only margin was {pbp_margin:+.1f}; actual margin was {actual_margin:+.1f} "
                    f"(gap {actual_margin - pbp_margin:+.1f})."
                ),
                "weight": abs(actual_margin - pbp_margin),
            }
        )
        if abs(nfelo_shift) >= 0.5:
            causes.append(
                {
                    "label": "nfelo_adjustment",
                    "detail": (
                        f"nfelo blend shifted margin by {nfelo_shift:+.1f} "
                        f"(PBP {pbp_margin:+.1f} -> nfelo {nfelo_margin:+.1f})."
                    ),
                    "weight": abs(nfelo_shift),
                }
            )
        if abs(market_shift) >= 0.5:
            causes.append(
                {
                    "label": "market_calibration",
                    "detail": (
                        f"Market blend shifted margin by {market_shift:+.1f} "
                        f"(nfelo {nfelo_margin:+.1f} -> market {market_margin:+.1f})."
                    ),
                    "weight": abs(market_shift),
                }
            )

    if total_miss:
        nfelo_total_shift = nfelo_total - pbp_total
        market_total_shift = market_total - nfelo_total
        causes.append(
            {
                "label": "score_projection_error",
                "detail": (
                    f"Projected total {final_total:.1f} vs actual {actual_total:.1f} "
                    f"(error {actual_total - final_total:+.1f})."
                ),
                "weight": abs(actual_total - final_total),
            }
        )
        if abs(nfelo_total_shift) >= 0.5:
            causes.append(
                {
                    "label": "nfelo_adjustment",
                    "detail": f"nfelo shifted expected total by {nfelo_total_shift:+.1f}.",
                    "weight": abs(nfelo_total_shift),
                }
            )
        if abs(market_total_shift) >= 0.5:
            causes.append(
                {
                    "label": "market_calibration",
                    "detail": f"Market blend shifted expected total by {market_total_shift:+.1f}.",
                    "weight": abs(market_total_shift),
                }
            )

    low_sample_teams = [
        team
        for team, profile in (("home", home_profile), ("away", away_profile))
        if _safe_int(profile.get("games")) < LOW_PROFILE_GAMES_THRESHOLD
    ]
    if low_sample_teams:
        causes.append(
            {
                "label": "low_profile_sample",
                "detail": (
                    "Training profiles had fewer than "
                    f"{LOW_PROFILE_GAMES_THRESHOLD} games for: {', '.join(low_sample_teams)}."
                ),
                "weight": float(LOW_PROFILE_GAMES_THRESHOLD),
            }
        )

    turnovers = [
        (team, count)
        for team, count in (
            (_row_get(grade, "home_abbr"), game_summary.get("home_turnovers")),
            (_row_get(grade, "away_abbr"), game_summary.get("away_turnovers")),
        )
        if count is not None and int(count) >= HIGH_TURNOVER_THRESHOLD
    ]
    if turnovers:
        detail = ", ".join(f"{team}={count}" for team, count in turnovers)
        causes.append(
            {
                "label": "turnover_variance",
                "detail": f"High turnovers in actual game ({detail}).",
                "weight": float(max(int(count) for _, count in turnovers)),
            }
        )

    for team, shift in (
        (_row_get(grade, "home_abbr"), home_pf_shift),
        (_row_get(grade, "away_abbr"), away_pf_shift),
    ):
        if shift is not None and abs(shift) >= 1.0:
            causes.append(
                {
                    "label": "single_game_profile_swing",
                    "detail": f"Including this game would move {team} PF mean by {shift:+.1f}.",
                    "weight": abs(shift),
                }
            )

    causes.sort(key=lambda item: float(item["weight"]), reverse=True)
    return causes


def analyze_missed_pick(
    grade: Any,
    *,
    pbp: pd.DataFrame,
    game_pbp: pd.DataFrame | None = None,
    nfelo_games: pd.DataFrame | None = None,
    nfelo_lookup: dict[str, float] | None = None,
    current_pbp_season: int | None = None,
) -> dict[str, Any]:
    """Reconstruct training inputs and explain why a graded pick missed."""
    if not is_missed_grade(grade):
        raise ValueError("analyze_missed_pick requires a missed spread or total grade")

    home_team = str(_row_get(grade, "home_abbr"))
    away_team = str(_row_get(grade, "away_abbr"))
    game_id = str(_row_get(grade, "game_id"))
    season = int(_row_get(grade, "season"))
    week = int(_row_get(grade, "week"))
    prior_season = int(_row_get(grade, "pbp_season") or (season - 1))
    current_season = current_pbp_season or season

    config = SimulationConfig(
        market_blend=float(_row_get(grade, "market_blend") or DEFAULT_MARKET_BLEND),
        nfelo_blend=float(_row_get(grade, "nfelo_blend") or DEFAULT_NFELO_BLEND),
        home_field_advantage=float(
            _row_get(grade, "home_field_advantage") or DEFAULT_HOME_FIELD_ADVANTAGE
        ),
    )

    training_pbp = filter_training_pbp(
        pbp,
        prior_season=prior_season,
        current_season=current_season,
        before_week=week,
        exclude_game_ids={game_id},
    )
    profiles = compute_team_scoring_profiles(training_pbp)
    home_profile = _profile_snapshot(profiles, home_team)
    away_profile = _profile_snapshot(profiles, away_team)
    profile_source = "reconstructed"
    projection_source = "reconstructed"

    home_spread = _safe_float(_row_get(grade, "home_spread"))
    total_line = _safe_float(_row_get(grade, "total_line"))
    lookup = nfelo_lookup or {}
    nfelo_game = nfelo_games_lookup(nfelo_games).get(game_id) if nfelo_games is not None else None

    snapshot_stages = _snapshot_projection_stages(grade)
    if snapshot_stages is not None:
        stages = snapshot_stages
        projection_source = "snapshot"
    else:
        stages = _projection_stages(
            home_team=home_team,
            away_team=away_team,
            profiles=profiles,
            home_spread=home_spread,
            total_line=total_line,
            config=config,
            game_id=game_id,
            nfelo_game=nfelo_game,
            nfelo_lookup=lookup,
        )
        projection_source = "reconstructed"

    snapshot_profiles = _snapshot_profiles(grade)
    if snapshot_profiles is not None:
        home_profile, away_profile = snapshot_profiles
        profile_source = "snapshot"

    actual_home = float(_row_get(grade, "actual_home_score"))
    actual_away = float(_row_get(grade, "actual_away_score"))

    game_summary = summarize_game_pbp(
        game_pbp if game_pbp is not None else pd.DataFrame(),
        home_team=home_team,
        away_team=away_team,
    )

    home_pf_shift = _profile_shift_if_game_included(
        training_pbp,
        team=home_team,
        game_id=game_id,
        points_for=actual_home,
        points_against=actual_away,
    )
    away_pf_shift = _profile_shift_if_game_included(
        training_pbp,
        team=away_team,
        game_id=game_id,
        points_for=actual_away,
        points_against=actual_home,
    )

    causes = _rank_causes(
        grade=grade,
        stages=stages,
        actual_home=actual_home,
        actual_away=actual_away,
        home_profile=home_profile,
        away_profile=away_profile,
        game_summary=game_summary,
        home_pf_shift=home_pf_shift,
        away_pf_shift=away_pf_shift,
    )
    primary_cause = causes[0]["label"] if causes else "unknown"

    return {
        "grade_id": _row_get(grade, "grade_id"),
        "prediction_id": _row_get(grade, "prediction_id"),
        "game_id": game_id,
        "season": season,
        "week": week,
        "miss_types": _miss_types(grade),
        "primary_cause": primary_cause,
        "pbp_proj_home": stages["pbp_home"],
        "pbp_proj_away": stages["pbp_away"],
        "nfelo_proj_home": stages["nfelo_home"],
        "nfelo_proj_away": stages["nfelo_away"],
        "market_proj_home": stages["market_home"],
        "market_proj_away": stages["market_away"],
        "actual_home": actual_home,
        "actual_away": actual_away,
        "home_profile_games": home_profile["games"],
        "home_profile_pf_mean": home_profile["points_for_mean"],
        "home_profile_pa_mean": home_profile["points_against_mean"],
        "away_profile_games": away_profile["games"],
        "away_profile_pf_mean": away_profile["points_for_mean"],
        "away_profile_pa_mean": away_profile["points_against_mean"],
        "game_play_count": game_summary["play_count"],
        "game_home_turnovers": game_summary["home_turnovers"],
        "game_away_turnovers": game_summary["away_turnovers"],
        "game_home_epa": game_summary["home_epa"],
        "game_away_epa": game_summary["away_epa"],
        "profile_source": profile_source,
        "projection_source": projection_source,
        "cause_summary": json.dumps(causes),
    }


def _safe_int(value: Any, default: int = 0) -> int:
    """Coerce to int; treat None/NaN as default (NaN is truthy so `x or 0` fails)."""
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _snapshot_profiles(grade: Any) -> tuple[dict[str, float | int | None], dict[str, float | int | None]] | None:
    home_games = _row_get(grade, "home_profile_games")
    away_games = _row_get(grade, "away_profile_games")
    if home_games is None and away_games is None:
        return None
    try:
        if pd.isna(home_games) and pd.isna(away_games):
            return None
    except (TypeError, ValueError):
        pass
    return (
        {
            "games": _safe_int(home_games),
            "points_for_mean": _safe_float(_row_get(grade, "home_profile_pf_mean")),
            "points_against_mean": _safe_float(_row_get(grade, "home_profile_pa_mean")),
        },
        {
            "games": _safe_int(away_games),
            "points_for_mean": _safe_float(_row_get(grade, "away_profile_pf_mean")),
            "points_against_mean": _safe_float(_row_get(grade, "away_profile_pa_mean")),
        },
    )


def _snapshot_projection_stages(grade: Any) -> dict[str, float] | None:
    pbp_home = _safe_float(_row_get(grade, "pbp_proj_home"))
    pbp_away = _safe_float(_row_get(grade, "pbp_proj_away"))
    if pbp_home is None or pbp_away is None:
        return None
    return {
        "pbp_home": round(pbp_home, 2),
        "pbp_away": round(pbp_away, 2),
        "nfelo_home": round(_safe_float(_row_get(grade, "nfelo_proj_home")) or pbp_home, 2),
        "nfelo_away": round(_safe_float(_row_get(grade, "nfelo_proj_away")) or pbp_away, 2),
        "market_home": round(_safe_float(_row_get(grade, "market_proj_home")) or pbp_home, 2),
        "market_away": round(_safe_float(_row_get(grade, "market_proj_away")) or pbp_away, 2),
    }


def analyze_missed_grades(
    grades: pd.DataFrame,
    *,
    pbp: pd.DataFrame,
    game_pbp_by_id: dict[str, pd.DataFrame] | None = None,
    nfelo_games: pd.DataFrame | None = None,
    nfelo_lookup: dict[str, float] | None = None,
    current_pbp_season: int | None = None,
) -> pd.DataFrame:
    """Analyze every missed pick in a graded batch."""
    missed = filter_missed_grades(grades)
    if missed.empty:
        return pd.DataFrame()

    game_pbp_by_id = game_pbp_by_id or {}
    rows: list[dict[str, Any]] = []
    for grade in missed.to_dict(orient="records"):
        game_id = str(grade["game_id"])
        rows.append(
            analyze_missed_pick(
                grade,
                pbp=pbp,
                game_pbp=game_pbp_by_id.get(game_id),
                nfelo_games=nfelo_games,
                nfelo_lookup=nfelo_lookup,
                current_pbp_season=current_pbp_season,
            )
        )
    return pd.DataFrame(rows)


def prepare_rca_log(
    reports: pd.DataFrame,
    *,
    rca_run_id: str,
    grading_run_id: str | None = None,
    analyzed_at: datetime | None = None,
) -> pd.DataFrame:
    """Attach run metadata before persisting RCA rows."""
    if reports.empty:
        return pd.DataFrame()

    stamped = analyzed_at or datetime.now(timezone.utc)
    logged = reports.copy()
    logged["rca_id"] = [str(uuid4()) for _ in range(len(logged))]
    logged["rca_run_id"] = rca_run_id
    logged["grading_run_id"] = grading_run_id
    logged["analyzed_at"] = stamped.isoformat()
    return logged