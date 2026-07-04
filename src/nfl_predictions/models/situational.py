"""Situational total adjustments from schedule context."""

from __future__ import annotations

import pandas as pd

from nfl_predictions.simulation import expected_matchup_scores
from nfl_predictions.models.common import (
    ModelConfig,
    build_pick_row,
    filter_week_games,
    market_margin_from_spread,
    normal_spread_probs,
    normal_total_probs,
)

DIVISION_TOTAL_ADJ = -1.0
DOME_TOTAL_ADJ = 1.5
OUTDOOR_COLD_ADJ = -2.0
COLD_TEMP_F = 40.0


def situational_total_adjustment(game: object) -> float:
    """Return points adjustment for projected game total."""
    adjustment = 0.0
    div_game = getattr(game, "div_game", None)
    if div_game is not None and bool(div_game):
        adjustment += DIVISION_TOTAL_ADJ

    roof = str(getattr(game, "roof", "") or "").lower()
    if roof in {"dome", "closed"}:
        adjustment += DOME_TOTAL_ADJ

    temp = getattr(game, "temp", None)
    if temp is not None:
        try:
            if float(temp) < COLD_TEMP_F and roof not in {"dome", "closed"}:
                adjustment += OUTDOOR_COLD_ADJ
        except (TypeError, ValueError):
            pass

    wind = getattr(game, "wind", None)
    if wind is not None:
        try:
            if float(wind) >= 15 and roof not in {"dome", "closed"}:
                adjustment -= 1.0
        except (TypeError, ValueError):
            pass

    return adjustment


def enrich_games_with_schedule(
    odds_games: pd.DataFrame,
    schedule: pd.DataFrame | None,
) -> pd.DataFrame:
    """Attach schedule situational columns to odds rows."""
    if schedule is None or schedule.empty or "game_id" not in odds_games.columns:
        return odds_games.copy()

    situational_cols = [
        col
        for col in ("div_game", "roof", "surface", "temp", "wind")
        if col in schedule.columns
    ]
    if not situational_cols:
        return odds_games.copy()

    meta = schedule[["game_id", *situational_cols]].drop_duplicates(subset=["game_id"])
    return odds_games.merge(meta, on="game_id", how="left")


def predict_situational_week(
    odds_games: pd.DataFrame,
    profiles: pd.DataFrame,
    *,
    week: int,
    schedule: pd.DataFrame | None = None,
    config: ModelConfig | None = None,
    include_completed: bool = False,
) -> pd.DataFrame:
    """Profile-based picks with situational total adjustments."""
    cfg = config or ModelConfig()
    enriched = enrich_games_with_schedule(odds_games, schedule)
    games = filter_week_games(
        enriched,
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
        total_adj = situational_total_adjustment(game)
        half_adj = total_adj / 2.0
        proj_home += half_adj
        proj_away += half_adj

        margin = proj_home - proj_away
        market_margin = market_margin_from_spread(getattr(game, "home_spread", None))
        away_cover = home_cover = None
        if market_margin is not None:
            away_cover, home_cover = normal_spread_probs(margin, market_margin)

        total_line = getattr(game, "total_line", None)
        over_pct, under_pct = normal_total_probs(proj_home + proj_away, total_line)

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
                model_id="situational_total",
                extra={"situational_total_adj": round(total_adj, 2)},
            )
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["gameday", "kickoff_et", "game_id"],
        na_position="last",
    ).reset_index(drop=True)