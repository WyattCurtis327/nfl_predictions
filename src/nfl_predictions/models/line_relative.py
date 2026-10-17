"""Line-relative logistic model (numpy-only, no sklearn)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from nfl_predictions.simulation import (
    _game_results_from_pbp,
    expected_matchup_scores,
    resolve_spread_result,
    resolve_total_result,
)
from nfl_predictions.models.common import (
    ModelConfig,
    build_pick_row,
    filter_week_games,
    market_margin_from_spread,
)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


def fit_logistic(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    learning_rate: float = 0.1,
    epochs: int = 400,
    l2: float = 0.01,
) -> np.ndarray:
    """Train binary logistic regression with gradient descent."""
    if features.size == 0 or len(labels) == 0:
        return np.zeros(features.shape[1] if features.ndim == 2 else 1)

    x = np.asarray(features, dtype=float)
    y = np.asarray(labels, dtype=float)
    weights = np.zeros(x.shape[1], dtype=float)

    for _ in range(epochs):
        preds = _sigmoid(x @ weights)
        error = preds - y
        grad = (x.T @ error) / len(y) + l2 * weights
        weights -= learning_rate * grad
    return weights


def build_training_frame(
    pbp: pd.DataFrame,
    odds_history: pd.DataFrame,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Build spread/total training matrices from completed games with lines."""
    games = _game_results_from_pbp(pbp)
    if games.empty or odds_history.empty:
        return (
            np.empty((0, 4)),
            np.empty(0),
            np.empty((0, 2)),
            np.empty(0),
        )

    odds = odds_history.copy()
    if "spread_line" in odds.columns and "home_spread" not in odds.columns:
        odds["home_spread"] = -odds["spread_line"]
        odds["away_spread"] = odds["spread_line"]

    merged = games.merge(
        odds.drop_duplicates(subset=["game_id"], keep="last"),
        on="game_id",
        how="inner",
    )
    if merged.empty:
        return (
            np.empty((0, 4)),
            np.empty(0),
            np.empty((0, 2)),
            np.empty(0),
        )

    spread_features: list[list[float]] = []
    spread_labels: list[float] = []
    total_features: list[list[float]] = []
    total_labels: list[float] = []

    for row in merged.itertuples(index=False):
        home_spread = getattr(row, "home_spread", None)
        away_spread = getattr(row, "away_spread", None)
        total_line = getattr(row, "total_line", None)
        if home_spread is None or away_spread is None:
            continue

        actual_total = float(row.home_score) + float(row.away_score)
        spread_result = resolve_spread_result(
            float(row.away_score),
            float(row.home_score),
            away_spread=float(away_spread),
            home_spread=float(home_spread),
        )
        if spread_result == "push":
            continue

        market_margin = -float(home_spread)
        actual_margin = float(row.home_score) - float(row.away_score)
        spread_features.append(
            [
                actual_margin - market_margin,
                market_margin,
                float(home_spread),
                actual_total - float(total_line) if total_line is not None else 0.0,
            ]
        )
        spread_labels.append(1.0 if spread_result == "home" else 0.0)

        if total_line is not None:
            total_result = resolve_total_result(actual_total, float(total_line))
            if total_result != "push":
                total_features.append([float(total_line), actual_total - float(total_line)])
                total_labels.append(1.0 if total_result == "over" else 0.0)

    return (
        np.asarray(spread_features, dtype=float),
        np.asarray(spread_labels, dtype=float),
        np.asarray(total_features, dtype=float),
        np.asarray(total_labels, dtype=float),
    )


def predict_line_relative_week(
    odds_games: pd.DataFrame,
    profiles: pd.DataFrame,
    *,
    week: int,
    training_pbp: pd.DataFrame,
    training_odds: pd.DataFrame,
    schedule: pd.DataFrame | None = None,
    config: ModelConfig | None = None,
    include_completed: bool = False,
) -> pd.DataFrame:
    """ATS/O-U picks from a line-relative logistic model."""
    cfg = config or ModelConfig()
    spread_x, spread_y, total_x, total_y = build_training_frame(
        training_pbp,
        training_odds,
    )
    spread_weights = fit_logistic(spread_x, spread_y) if len(spread_y) >= 20 else None
    total_weights = fit_logistic(total_x, total_y) if len(total_y) >= 20 else None

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

        proj_home, proj_away, _, _ = expected_matchup_scores(
            str(home_abbr),
            str(away_abbr),
            profiles,
            home_field_advantage=cfg.home_field_advantage,
        )
        margin = proj_home - proj_away
        home_spread = getattr(game, "home_spread", None)
        total_line = getattr(game, "total_line", None)
        market_margin = market_margin_from_spread(home_spread)

        away_cover = home_cover = None
        if spread_weights is not None and market_margin is not None and home_spread is not None:
            edge = margin - market_margin
            features = np.array(
                [[edge, market_margin, float(home_spread), 0.0]],
                dtype=float,
            )
            home_cover = float(_sigmoid(features @ spread_weights)[0])
            away_cover = 1.0 - home_cover

        over_pct = under_pct = None
        if total_weights is not None and total_line is not None:
            features = np.array([[float(total_line), 0.0]], dtype=float)
            over_pct = float(_sigmoid(features @ total_weights)[0])
            under_pct = 1.0 - over_pct

        rows.append(
            build_pick_row(
                game,
                week=week,
                proj_home=proj_home,
                proj_away=proj_away,
                away_cover_pct=away_cover,
                home_cover_pct=home_cover,
                over_pct=over_pct,
                under_pct=under_pct,
                profiles=profiles,
                config=cfg,
                model_id="line_relative",
            )
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["gameday", "kickoff_et", "game_id"],
        na_position="last",
    ).reset_index(drop=True)