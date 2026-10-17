"""Poisson score model for spread and total probabilities."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from nfl_predictions.simulation import expected_matchup_scores
from nfl_predictions.models.common import (
    ModelConfig,
    build_pick_row,
    filter_week_games,
)


def _poisson_cover_probs(
    lambda_home: float,
    lambda_away: float,
    *,
    home_spread: float | None,
    away_spread: float | None,
    max_points: int = 60,
) -> tuple[float | None, float | None]:
    if home_spread is None or away_spread is None:
        return None, None

    home_rates = np.array([_poisson_pmf(lambda_home, k) for k in range(max_points + 1)])
    away_rates = np.array([_poisson_pmf(lambda_away, k) for k in range(max_points + 1)])
    joint = np.outer(home_rates, away_rates)

    home_idx = np.arange(max_points + 1)[:, None]
    away_idx = np.arange(max_points + 1)[None, :]
    away_covers = (away_idx + away_spread) > home_idx
    home_covers = (home_idx + home_spread) > away_idx

    away_prob = float(joint[away_covers].sum())
    home_prob = float(joint[home_covers].sum())
    return away_prob, home_prob


def _poisson_total_probs(
    lambda_home: float,
    lambda_away: float,
    total_line: float,
    *,
    max_points: int = 60,
) -> tuple[float, float]:
    home_rates = np.array([_poisson_pmf(lambda_home, k) for k in range(max_points + 1)])
    away_rates = np.array([_poisson_pmf(lambda_away, k) for k in range(max_points + 1)])
    joint = np.outer(home_rates, away_rates)

    totals = np.add.outer(np.arange(max_points + 1), np.arange(max_points + 1))
    over = float(joint[totals > total_line].sum())
    under = float(joint[totals < total_line].sum())
    return over, under


def _poisson_pmf(rate: float, k: int) -> float:
    rate = max(rate, 0.1)
    return float(math.exp(-rate) * (rate**k) / float(math.factorial(k)))


def predict_poisson_week(
    odds_games: pd.DataFrame,
    profiles: pd.DataFrame,
    *,
    week: int,
    schedule: pd.DataFrame | None = None,
    config: ModelConfig | None = None,
    include_completed: bool = False,
) -> pd.DataFrame:
    """Analytic Poisson model using profile-derived scoring rates."""
    cfg = config or ModelConfig()
    games = filter_week_games(
        odds_games,
        week=week,
        schedule=schedule,
        include_completed=include_completed,
    )
    if games.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for game in games.itertuples(index=False):
        home_abbr = getattr(game, "home_abbr", None) or getattr(game, "home_team", None)
        away_abbr = getattr(game, "away_abbr", None) or getattr(game, "away_team", None)
        if not home_abbr or not away_abbr:
            continue

        home_mu, away_mu, _, _ = expected_matchup_scores(
            str(home_abbr),
            str(away_abbr),
            profiles,
            home_field_advantage=cfg.home_field_advantage,
        )
        lambda_home = max(home_mu, 0.5)
        lambda_away = max(away_mu, 0.5)

        away_cover, home_cover = _poisson_cover_probs(
            lambda_home,
            lambda_away,
            home_spread=getattr(game, "home_spread", None),
            away_spread=getattr(game, "away_spread", None),
        )
        total_line = getattr(game, "total_line", None)
        over_pct = under_pct = None
        if total_line is not None:
            over_pct, under_pct = _poisson_total_probs(
                lambda_home,
                lambda_away,
                float(total_line),
            )

        rows.append(
            build_pick_row(
                game,
                week=week,
                proj_home=lambda_home,
                proj_away=lambda_away,
                away_cover_pct=away_cover,
                home_cover_pct=home_cover,
                over_pct=over_pct,
                under_pct=under_pct,
                profiles=profiles,
                config=cfg,
                model_id="poisson",
            )
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["gameday", "kickoff_et", "game_id"],
        na_position="last",
    ).reset_index(drop=True)