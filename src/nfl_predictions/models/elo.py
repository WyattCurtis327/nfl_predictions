"""Custom Elo ratings from completed game results."""

from __future__ import annotations

import pandas as pd

from nfl_predictions.simulation import _game_results_from_pbp
from nfl_predictions.models.common import (
    ModelConfig,
    build_pick_row,
    filter_week_games,
    market_margin_from_spread,
    normal_spread_probs,
    normal_total_probs,
)

DEFAULT_ELO = 1500.0
DEFAULT_K = 20.0
ELO_HOME_ADVANTAGE = 48.0
ELO_MARGIN_SCALE = 25.0


def compute_elo_ratings(
    pbp: pd.DataFrame,
    *,
    initial_rating: float = DEFAULT_ELO,
    k_factor: float = DEFAULT_K,
    home_advantage: float = ELO_HOME_ADVANTAGE,
) -> pd.DataFrame:
    """Replay completed games chronologically and return final Elo per team."""
    games = _game_results_from_pbp(pbp)
    if games.empty:
        return pd.DataFrame(columns=["team", "elo", "games"])

    if "gameday" in pbp.columns:
        meta = (
            pbp.groupby("game_id", as_index=False)
            .agg(gameday=("gameday", "first"), week=("week", "first"))
        )
        games = games.merge(meta, on="game_id", how="left")
        games = games.sort_values(["gameday", "week", "game_id"], na_position="last")
    else:
        games = games.sort_values("game_id")

    ratings: dict[str, float] = {}
    games_played: dict[str, int] = {}

    for row in games.itertuples(index=False):
        home = str(row.home_team)
        away = str(row.away_team)
        home_elo = ratings.get(home, initial_rating)
        away_elo = ratings.get(away, initial_rating)

        home_expected = _expected_score(home_elo + home_advantage, away_elo)
        away_expected = 1.0 - home_expected

        if row.home_score > row.away_score:
            home_actual, away_actual = 1.0, 0.0
        elif row.home_score < row.away_score:
            home_actual, away_actual = 0.0, 1.0
        else:
            home_actual = away_actual = 0.5

        ratings[home] = home_elo + k_factor * (home_actual - home_expected)
        ratings[away] = away_elo + k_factor * (away_actual - away_expected)
        games_played[home] = games_played.get(home, 0) + 1
        games_played[away] = games_played.get(away, 0) + 1

    return pd.DataFrame(
        [
            {"team": team, "elo": round(rating, 1), "games": games_played.get(team, 0)}
            for team, rating in sorted(ratings.items())
        ]
    )


def _expected_score(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


def _elo_projected_margin(
    home_team: str,
    away_team: str,
    ratings: pd.DataFrame,
    *,
    home_advantage: float = ELO_HOME_ADVANTAGE,
    margin_scale: float = ELO_MARGIN_SCALE,
) -> tuple[float, float, float]:
    lookup = {row.team: float(row.elo) for row in ratings.itertuples(index=False)}
    home_elo = lookup.get(home_team, DEFAULT_ELO)
    away_elo = lookup.get(away_team, DEFAULT_ELO)
    margin = (home_elo + home_advantage - away_elo) / margin_scale
    league_total = 44.0
    home_score = (league_total + margin) / 2.0
    away_score = (league_total - margin) / 2.0
    return home_score, away_score, margin


def predict_elo_week(
    odds_games: pd.DataFrame,
    profiles: pd.DataFrame,
    *,
    week: int,
    elo_ratings: pd.DataFrame,
    schedule: pd.DataFrame | None = None,
    config: ModelConfig | None = None,
    include_completed: bool = False,
) -> pd.DataFrame:
    """Spread/total picks from Elo-implied margins."""
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

        proj_home, proj_away, margin = _elo_projected_margin(
            str(home_abbr),
            str(away_abbr),
            elo_ratings,
        )
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
                model_id="elo",
                extra={"elo_proj_margin": round(margin, 2)},
            )
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["gameday", "kickoff_et", "game_id"],
        na_position="last",
    ).reset_index(drop=True)