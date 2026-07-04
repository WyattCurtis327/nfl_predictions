"""Model registry and multi-model orchestration."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from nfl_predictions.models.common import DEFAULT_MODEL_ID, MODEL_IDS, ModelConfig
from nfl_predictions.models.elo import compute_elo_ratings, predict_elo_week
from nfl_predictions.models.epa import compute_team_epa_profiles, predict_epa_margin_week
from nfl_predictions.models.ensemble import blend_model_predictions
from nfl_predictions.models.line_relative import predict_line_relative_week
from nfl_predictions.models.poisson import predict_poisson_week
from nfl_predictions.models.shrinkage import predict_shrinkage_week
from nfl_predictions.models.situational import predict_situational_week
from nfl_predictions.simulation import SimulationConfig, simulate_weekly_picks

__all__ = [
    "DEFAULT_MODEL_ID",
    "MODEL_IDS",
    "ModelRunContext",
    "run_all_models",
    "run_model",
]


@dataclass(frozen=True)
class ModelRunContext:
    odds_games: pd.DataFrame
    profiles: pd.DataFrame
    week: int
    schedule: pd.DataFrame | None = None
    pbp: pd.DataFrame | None = None
    training_odds: pd.DataFrame | None = None
    config: ModelConfig | None = None
    simulation_config: SimulationConfig | None = None
    nfelo_ratings: pd.DataFrame | None = None
    nfelo_games: pd.DataFrame | None = None
    include_completed: bool = False
    ensemble_weights: dict[str, float] | None = None


def run_model(
    model_id: str,
    ctx: ModelRunContext,
) -> pd.DataFrame:
    """Run a single model family and return standardized pick rows."""
    cfg = ctx.config or ModelConfig()
    if model_id == "monte_carlo":
        sim_cfg = ctx.simulation_config or SimulationConfig(
            pick_threshold=cfg.pick_threshold,
            home_field_advantage=cfg.home_field_advantage,
            random_seed=cfg.random_seed,
        )
        picks = simulate_weekly_picks(
            ctx.odds_games,
            ctx.profiles,
            week=ctx.week,
            schedule=ctx.schedule,
            config=sim_cfg,
            include_completed=ctx.include_completed,
            nfelo_ratings=ctx.nfelo_ratings,
            nfelo_games=ctx.nfelo_games,
        )
        if picks.empty:
            return picks
        picks = picks.copy()
        picks["model_id"] = DEFAULT_MODEL_ID
        return picks

    if model_id == "poisson":
        return predict_poisson_week(
            ctx.odds_games,
            ctx.profiles,
            week=ctx.week,
            schedule=ctx.schedule,
            config=cfg,
            include_completed=ctx.include_completed,
        )

    if model_id == "elo":
        pbp = ctx.pbp if ctx.pbp is not None else pd.DataFrame()
        elo_ratings = compute_elo_ratings(pbp)
        return predict_elo_week(
            ctx.odds_games,
            ctx.profiles,
            week=ctx.week,
            elo_ratings=elo_ratings,
            schedule=ctx.schedule,
            config=cfg,
            include_completed=ctx.include_completed,
        )

    if model_id == "epa_margin":
        pbp = ctx.pbp if ctx.pbp is not None else pd.DataFrame()
        epa_profiles = compute_team_epa_profiles(pbp)
        return predict_epa_margin_week(
            ctx.odds_games,
            ctx.profiles,
            week=ctx.week,
            epa_profiles=epa_profiles,
            schedule=ctx.schedule,
            config=cfg,
            include_completed=ctx.include_completed,
        )

    if model_id == "line_relative":
        pbp = ctx.pbp if ctx.pbp is not None else pd.DataFrame()
        training_odds = ctx.training_odds if ctx.training_odds is not None else ctx.odds_games
        return predict_line_relative_week(
            ctx.odds_games,
            ctx.profiles,
            week=ctx.week,
            training_pbp=pbp,
            training_odds=training_odds,
            schedule=ctx.schedule,
            config=cfg,
            include_completed=ctx.include_completed,
        )

    if model_id == "shrinkage_profile":
        return predict_shrinkage_week(
            ctx.odds_games,
            ctx.profiles,
            week=ctx.week,
            schedule=ctx.schedule,
            config=cfg,
            include_completed=ctx.include_completed,
        )

    if model_id == "situational_total":
        return predict_situational_week(
            ctx.odds_games,
            ctx.profiles,
            week=ctx.week,
            schedule=ctx.schedule,
            config=cfg,
            include_completed=ctx.include_completed,
        )

    if model_id == "ensemble":
        base_models = [mid for mid in MODEL_IDS if mid != "ensemble"]
        frames: dict[str, pd.DataFrame] = {}
        for mid in base_models:
            frame = run_model(mid, ctx)
            if not frame.empty:
                frames[mid] = frame
        return blend_model_predictions(
            frames,
            profiles=ctx.profiles,
            config=cfg,
            weights=ctx.ensemble_weights,
        )

    raise ValueError(f"Unknown model_id: {model_id}")


def run_all_models(
    ctx: ModelRunContext,
    *,
    model_ids: tuple[str, ...] | list[str] | None = None,
) -> pd.DataFrame:
    """Run each requested model and concatenate results."""
    ids = tuple(model_ids) if model_ids is not None else MODEL_IDS
    frames: list[pd.DataFrame] = []
    for model_id in ids:
        if model_id == "ensemble":
            frame = run_model("ensemble", ctx)
        else:
            frame = run_model(model_id, ctx)
        if not frame.empty:
            frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)