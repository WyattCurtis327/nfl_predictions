"""EPA-based team strength model for spread probabilities."""

from __future__ import annotations

import pandas as pd

from nfl_predictions.models.common import (
    ModelConfig,
    build_pick_row,
    filter_week_games,
    market_margin_from_spread,
    normal_spread_probs,
    normal_total_probs,
)

EPA_MARGIN_SCALE = 7.0
LEAGUE_BASE_TOTAL = 44.0


def compute_team_epa_profiles(pbp: pd.DataFrame) -> pd.DataFrame:
    """Per-team offensive and defensive EPA per play from PBP."""
    required = {"posteam", "defteam", "epa", "play_type"}
    if pbp.empty or not required.issubset(pbp.columns):
        return pd.DataFrame(
            columns=["team", "plays", "off_epa_per_play", "def_epa_per_play", "net_epa"]
        )

    plays = pbp.copy()
    plays["epa"] = pd.to_numeric(plays["epa"], errors="coerce").fillna(0.0)
    offense = (
        plays.groupby("posteam", as_index=False)
        .agg(plays=("epa", "count"), off_epa_per_play=("epa", "mean"))
        .rename(columns={"posteam": "team"})
    )
    defense = (
        plays.groupby("defteam", as_index=False)
        .agg(def_epa_per_play=("epa", "mean"))
        .rename(columns={"defteam": "team"})
    )
    profiles = offense.merge(defense, on="team", how="outer").fillna(0.0)
    profiles["net_epa"] = profiles["off_epa_per_play"] - profiles["def_epa_per_play"]
    return profiles


def _epa_projected_scores(
    home_team: str,
    away_team: str,
    epa_profiles: pd.DataFrame,
    *,
    home_field_advantage: float,
    margin_scale: float = EPA_MARGIN_SCALE,
) -> tuple[float, float, float]:
    lookup = {
        row.team: row
        for row in epa_profiles.itertuples(index=False)
    }
    home = lookup.get(home_team)
    away = lookup.get(away_team)
    home_off = float(home.off_epa_per_play) if home is not None else 0.0
    home_def = float(home.def_epa_per_play) if home is not None else 0.0
    away_off = float(away.off_epa_per_play) if away is not None else 0.0
    away_def = float(away.def_epa_per_play) if away is not None else 0.0

    home_edge = home_off - away_def
    away_edge = away_off - home_def
    margin = (home_edge - away_edge) * margin_scale + home_field_advantage
    proj_home = (LEAGUE_BASE_TOTAL + margin) / 2.0
    proj_away = (LEAGUE_BASE_TOTAL - margin) / 2.0
    return proj_home, proj_away, margin


def predict_epa_margin_week(
    odds_games: pd.DataFrame,
    profiles: pd.DataFrame,
    *,
    week: int,
    epa_profiles: pd.DataFrame,
    schedule: pd.DataFrame | None = None,
    config: ModelConfig | None = None,
    include_completed: bool = False,
) -> pd.DataFrame:
    """Spread/total picks from EPA matchup edges."""
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

        proj_home, proj_away, margin = _epa_projected_scores(
            str(home_abbr),
            str(away_abbr),
            epa_profiles,
            home_field_advantage=cfg.home_field_advantage,
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
                model_id="epa_margin",
                extra={"epa_proj_margin": round(margin, 2)},
            )
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["gameday", "kickoff_et", "game_id"],
        na_position="last",
    ).reset_index(drop=True)