"""Shared types and pick-row builders for alternative models."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from nfl_predictions.simulation import (
    DEFAULT_HOME_FIELD_ADVANTAGE,
    DEFAULT_PICK_THRESHOLD,
    _pick_side,
    _pick_total,
    _round_pct,
    _safe_float,
    profile_snapshot,
)

DEFAULT_MODEL_ID = "monte_carlo"

MODEL_IDS: tuple[str, ...] = (
    "monte_carlo",
    "poisson",
    "elo",
    "epa_margin",
    "line_relative",
    "shrinkage_profile",
    "situational_total",
    "ensemble",
)


@dataclass(frozen=True)
class ModelConfig:
    pick_threshold: float = DEFAULT_PICK_THRESHOLD
    home_field_advantage: float = DEFAULT_HOME_FIELD_ADVANTAGE
    random_seed: int | None = 42


def filter_week_games(
    odds_games: pd.DataFrame,
    *,
    week: int,
    schedule: pd.DataFrame | None = None,
    include_completed: bool = False,
) -> pd.DataFrame:
    """Return odds rows for a week, optionally restricting to unplayed games."""
    if odds_games.empty:
        return odds_games.copy()

    games = odds_games.copy()
    if "week" in games.columns:
        games = games[games["week"] == week]
    if games.empty:
        return games

    if (
        not include_completed
        and schedule is not None
        and {"game_id", "home_score", "away_score"}.issubset(schedule.columns)
    ):
        unplayed = schedule[schedule["home_score"].isna() & schedule["away_score"].isna()]
        games = games.merge(unplayed[["game_id"]], on="game_id", how="inner")

    return games.reset_index(drop=True)


def build_pick_row(
    game: Any,
    *,
    week: int,
    proj_home: float,
    proj_away: float,
    away_cover_pct: float | None,
    home_cover_pct: float | None,
    over_pct: float | None,
    under_pct: float | None,
    profiles: pd.DataFrame,
    config: ModelConfig,
    model_id: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Standardize a single-game prediction row across model families."""
    home_abbr = getattr(game, "home_abbr", None) or getattr(game, "home_team", None)
    away_abbr = getattr(game, "away_abbr", None) or getattr(game, "away_team", None)

    spread_pick, spread_conf, spread_side = _pick_side(
        str(away_abbr),
        str(home_abbr),
        away_cover_pct,
        home_cover_pct,
        config.pick_threshold,
    )
    total_pick, total_conf = _pick_total(over_pct, under_pct, config.pick_threshold)

    home_profile = profile_snapshot(profiles, str(home_abbr))
    away_profile = profile_snapshot(profiles, str(away_abbr))

    row: dict[str, Any] = {
        "model_id": model_id,
        "game_id": getattr(game, "game_id", None),
        "week": week,
        "game_type": getattr(game, "game_type", None),
        "gameday": getattr(game, "gameday", None),
        "kickoff_et": getattr(game, "kickoff_et", None),
        "away_abbr": away_abbr,
        "home_abbr": home_abbr,
        "away_spread": getattr(game, "away_spread", None),
        "home_spread": getattr(game, "home_spread", None),
        "total_line": getattr(game, "total_line", None),
        "bookmaker": getattr(game, "bookmaker", None),
        "pbp_proj_home": round(proj_home, 2),
        "pbp_proj_away": round(proj_away, 2),
        "proj_home_score": round(proj_home, 2),
        "proj_away_score": round(proj_away, 2),
        "proj_total": round(proj_home + proj_away, 2),
        "away_cover_pct": _round_pct(away_cover_pct),
        "home_cover_pct": _round_pct(home_cover_pct),
        "over_pct": _round_pct(over_pct),
        "under_pct": _round_pct(under_pct),
        "spread_pick": spread_pick,
        "spread_side": spread_side,
        "spread_confidence": _round_pct(spread_conf),
        "total_pick": total_pick,
        "total_confidence": _round_pct(total_conf),
        "home_profile_games": home_profile["games"],
        "home_profile_pf_mean": home_profile["points_for_mean"],
        "home_profile_pa_mean": home_profile["points_against_mean"],
        "away_profile_games": away_profile["games"],
        "away_profile_pf_mean": away_profile["points_for_mean"],
        "away_profile_pa_mean": away_profile["points_against_mean"],
        "pick_threshold": config.pick_threshold,
        "home_field_advantage": config.home_field_advantage,
        "n_simulations": None,
    }
    if extra:
        row.update(extra)
    return row


def normal_total_probs(
    proj_total: float,
    total_line: float | None,
    *,
    total_std: float = 10.0,
) -> tuple[float | None, float | None]:
    """Gaussian approximation for over/under probabilities."""
    if total_line is None:
        return None, None
    z = (total_line - proj_total) / max(total_std, 1.0)
    under = float(0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))
    over = 1.0 - under
    return over, under


def normal_spread_probs(
    proj_margin: float,
    market_margin: float,
    *,
    margin_std: float = 10.0,
) -> tuple[float, float]:
    """Return away/home cover probabilities from projected vs market margin."""
    edge = proj_margin - market_margin
    z = edge / max(margin_std, 1.0)
    home_cover = float(0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))
    away_cover = 1.0 - home_cover
    return away_cover, home_cover


def market_margin_from_spread(home_spread: float | None) -> float | None:
    if home_spread is None:
        return None
    return -float(home_spread)