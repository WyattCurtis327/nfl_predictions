"""Empirical-Bayes shrinkage on team scoring profiles."""

from __future__ import annotations

import pandas as pd

from nfl_predictions.simulation import (
    LEAGUE_SCORING_DEFAULTS,
    PROFILE_COLUMNS,
    expected_matchup_scores,
)
from nfl_predictions.models.common import (
    ModelConfig,
    build_pick_row,
    filter_week_games,
    market_margin_from_spread,
    normal_spread_probs,
    normal_total_probs,
)

DEFAULT_PRIOR_GAMES = 4.0


def shrink_team_profiles(
    profiles: pd.DataFrame,
    *,
    prior_games: float = DEFAULT_PRIOR_GAMES,
) -> pd.DataFrame:
    """Shrink team scoring means toward league averages by sample size."""
    if profiles.empty:
        return pd.DataFrame(columns=PROFILE_COLUMNS)

    shrunk = profiles.copy()
    league_pf = float(shrunk["points_for_mean"].mean())
    league_pa = float(shrunk["points_against_mean"].mean())
    weight = shrunk["games"] / (shrunk["games"] + prior_games)
    shrunk["points_for_mean"] = weight * shrunk["points_for_mean"] + (1 - weight) * league_pf
    shrunk["points_against_mean"] = (
        weight * shrunk["points_against_mean"] + (1 - weight) * league_pa
    )
    shrunk["points_for_std"] = shrunk["points_for_std"].fillna(
        LEAGUE_SCORING_DEFAULTS["points_for_std"]
    )
    shrunk["points_against_std"] = shrunk["points_against_std"].fillna(
        LEAGUE_SCORING_DEFAULTS["points_against_std"]
    )
    return shrunk


def predict_shrinkage_week(
    odds_games: pd.DataFrame,
    profiles: pd.DataFrame,
    *,
    week: int,
    schedule: pd.DataFrame | None = None,
    config: ModelConfig | None = None,
    include_completed: bool = False,
    prior_games: float = DEFAULT_PRIOR_GAMES,
) -> pd.DataFrame:
    """Profile-based picks with empirical-Bayes shrinkage for low-sample teams."""
    cfg = config or ModelConfig()
    shrunk_profiles = shrink_team_profiles(profiles, prior_games=prior_games)
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
            shrunk_profiles,
            home_field_advantage=cfg.home_field_advantage,
        )
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
                profiles=shrunk_profiles,
                config=cfg,
                model_id="shrinkage_profile",
                extra={"shrinkage_prior_games": prior_games},
            )
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["gameday", "kickoff_et", "game_id"],
        na_position="last",
    ).reset_index(drop=True)