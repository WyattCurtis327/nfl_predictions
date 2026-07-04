"""Blend multiple model outputs into a stacked ensemble pick."""

from __future__ import annotations

from collections import defaultdict

import pandas as pd

from nfl_predictions.models.common import (
    ModelConfig,
    build_pick_row,
)
from nfl_predictions.simulation import (
    _pick_side,
    _pick_total,
    _round_pct,
    profile_snapshot,
)

DEFAULT_ENSEMBLE_WEIGHTS: dict[str, float] = {
    "monte_carlo": 0.30,
    "poisson": 0.10,
    "elo": 0.10,
    "epa_margin": 0.15,
    "line_relative": 0.15,
    "shrinkage_profile": 0.10,
    "situational_total": 0.10,
}


def blend_model_predictions(
    model_frames: dict[str, pd.DataFrame],
    *,
    profiles: pd.DataFrame,
    config: ModelConfig | None = None,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Weighted-average cover/over probabilities across model families."""
    cfg = config or ModelConfig()
    blend_weights = weights or DEFAULT_ENSEMBLE_WEIGHTS

    by_game: dict[str, list[tuple[str, pd.Series]]] = defaultdict(list)
    for model_id, frame in model_frames.items():
        if frame is None or frame.empty:
            continue
        for row in frame.itertuples(index=False):
            game_id = getattr(row, "game_id", None)
            if game_id:
                by_game[str(game_id)].append((model_id, pd.Series(row._asdict())))

    rows: list[dict] = []
    for game_id, entries in by_game.items():
        if not entries:
            continue

        total_weight = 0.0
        away_cover = home_cover = over_pct = under_pct = 0.0
        proj_home = proj_away = 0.0
        template = entries[0][1]

        for model_id, series in entries:
            weight = blend_weights.get(model_id, 0.0)
            if weight <= 0:
                continue
            total_weight += weight
            away_cover += weight * float(series.get("away_cover_pct") or 0.5)
            home_cover += weight * float(series.get("home_cover_pct") or 0.5)
            over_pct += weight * float(series.get("over_pct") or 0.5)
            under_pct += weight * float(series.get("under_pct") or 0.5)
            proj_home += weight * float(series.get("proj_home_score") or 0.0)
            proj_away += weight * float(series.get("proj_away_score") or 0.0)

        if total_weight <= 0:
            continue

        away_cover /= total_weight
        home_cover /= total_weight
        over_pct /= total_weight
        under_pct /= total_weight
        proj_home /= total_weight
        proj_away /= total_weight

        spread_pick, spread_conf, spread_side = _pick_side(
            str(template.get("away_abbr")),
            str(template.get("home_abbr")),
            away_cover,
            home_cover,
            cfg.pick_threshold,
        )
        total_pick, total_conf = _pick_total(over_pct, under_pct, cfg.pick_threshold)

        home_profile = profile_snapshot(profiles, str(template.get("home_abbr")))
        away_profile = profile_snapshot(profiles, str(template.get("away_abbr")))

        rows.append(
            {
                "model_id": "ensemble",
                "game_id": game_id,
                "week": template.get("week"),
                "game_type": template.get("game_type"),
                "gameday": template.get("gameday"),
                "kickoff_et": template.get("kickoff_et"),
                "away_abbr": template.get("away_abbr"),
                "home_abbr": template.get("home_abbr"),
                "away_spread": template.get("away_spread"),
                "home_spread": template.get("home_spread"),
                "total_line": template.get("total_line"),
                "bookmaker": template.get("bookmaker"),
                "pbp_proj_home": round(proj_home, 2),
                "pbp_proj_away": round(proj_away, 2),
                "proj_home_score": round(proj_home, 2),
                "proj_away_score": round(proj_away, 2),
                "proj_total": round(proj_home + proj_away, 2),
                "away_cover_pct": _round_pct(away_cover),
                "home_cover_pct": _round_pct(home_cover),
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
                "pick_threshold": cfg.pick_threshold,
                "home_field_advantage": cfg.home_field_advantage,
                "n_simulations": None,
                "ensemble_models": ",".join(sorted({model for model, _ in entries})),
            }
        )

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["gameday", "kickoff_et", "game_id"],
        na_position="last",
    ).reset_index(drop=True)