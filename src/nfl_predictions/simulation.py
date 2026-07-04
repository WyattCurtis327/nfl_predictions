"""Monte Carlo game simulations for spread and total picks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

from nfl_predictions.nflverse_data import GAME_TYPES_REG_PLAYOFF

DEFAULT_HOME_FIELD_ADVANTAGE = 2.5
DEFAULT_MARKET_BLEND = 0.35
DEFAULT_PICK_THRESHOLD = 0.55
DEFAULT_SIMULATIONS = 10_000

LEAGUE_SCORING_DEFAULTS = {
    "points_for_mean": 22.5,
    "points_for_std": 10.0,
    "points_against_mean": 22.5,
    "points_against_std": 10.0,
}

PROFILE_COLUMNS = [
    "team",
    "games",
    "points_for_mean",
    "points_for_std",
    "points_against_mean",
    "points_against_std",
]


@dataclass(frozen=True)
class SimulationConfig:
    n_simulations: int = DEFAULT_SIMULATIONS
    home_field_advantage: float = DEFAULT_HOME_FIELD_ADVANTAGE
    market_blend: float = DEFAULT_MARKET_BLEND
    pick_threshold: float = DEFAULT_PICK_THRESHOLD
    random_seed: int | None = 42


def filter_schedule_game_types(
    schedule: pd.DataFrame,
    *,
    game_types: tuple[str, ...] | list[str] = GAME_TYPES_REG_PLAYOFF,
) -> pd.DataFrame:
    """Keep regular season and playoff games; exclude preseason."""
    if schedule.empty or "game_type" not in schedule.columns:
        return schedule.copy()
    return schedule[schedule["game_type"].isin(game_types)].copy()


def prepare_schedule_for_grading(schedule: pd.DataFrame) -> pd.DataFrame:
    """Map nflverse schedule columns to fields expected by ``grade_predictions``."""
    sched = schedule.copy()
    if "spread_line" in sched.columns:
        sched["away_spread"] = sched["spread_line"]
        sched["home_spread"] = -sched["spread_line"]
    if "away_team" in sched.columns and "away_abbr" not in sched.columns:
        sched["away_abbr"] = sched["away_team"]
    if "home_team" in sched.columns and "home_abbr" not in sched.columns:
        sched["home_abbr"] = sched["home_team"]
    return sched


def prepare_odds_for_simulation(
    odds: pd.DataFrame,
    *,
    preferred_bookmaker: str | None = None,
) -> pd.DataFrame:
    """Normalize ``game_odds_latest`` rows for ``simulate_weekly_picks``."""
    if odds.empty:
        return odds.copy()

    games = odds.copy()
    if preferred_bookmaker and "bookmaker" in games.columns:
        preferred = games[
            games["bookmaker"].astype(str).str.lower() == preferred_bookmaker.lower()
        ]
        if not preferred.empty:
            games = preferred.copy()
        elif "game_id" in games.columns:
            sort_col = "ingested_at" if "ingested_at" in games.columns else None
            if sort_col:
                games = games.sort_values(sort_col)
            games = games.drop_duplicates(subset=["game_id"], keep="last")

    if "spread_line" in games.columns:
        games["away_spread"] = games["spread_line"]
        games["home_spread"] = -games["spread_line"]
    if "away_team" in games.columns and "away_abbr" not in games.columns:
        games["away_abbr"] = games["away_team"]
    if "home_team" in games.columns and "home_abbr" not in games.columns:
        games["home_abbr"] = games["home_team"]
    return games.reset_index(drop=True)


def _game_results_from_pbp(pbp: pd.DataFrame) -> pd.DataFrame:
    """One row per game with final scores."""
    required = {"game_id", "home_team", "away_team", "total_home_score", "total_away_score"}
    if pbp.empty or not required.issubset(pbp.columns):
        return pd.DataFrame(
            columns=["game_id", "home_team", "away_team", "home_score", "away_score"]
        )

    games = (
        pbp.groupby("game_id", as_index=False)
        .agg(
            home_team=("home_team", "first"),
            away_team=("away_team", "first"),
            home_score=("total_home_score", "max"),
            away_score=("total_away_score", "max"),
        )
        .dropna(subset=["home_score", "away_score"])
    )
    return games


def combine_pbp_seasons(
    prior_pbp: pd.DataFrame,
    current_pbp: pd.DataFrame,
    *,
    prior_season: int | None = None,
    current_season: int | None = None,
) -> pd.DataFrame:
    """Merge prior and in-season PBP; current-season rows win on duplicate game_id."""
    frames: list[pd.DataFrame] = []

    if prior_pbp is not None and not prior_pbp.empty:
        prior = prior_pbp.copy()
        if prior_season is not None and "season" in prior.columns:
            prior = prior[prior["season"] == prior_season]
        if not prior.empty:
            frames.append(prior)

    if current_pbp is not None and not current_pbp.empty:
        current = current_pbp.copy()
        if current_season is not None and "season" in current.columns:
            current = current[current["season"] == current_season]
        if not current.empty:
            frames.append(current)

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    if "game_id" in combined.columns and len(frames) > 1:
        combined = combined.drop_duplicates(subset=["game_id"], keep="last")
    return combined


def compute_team_scoring_profiles(pbp: pd.DataFrame) -> pd.DataFrame:
    """Derive per-team scoring means and volatility from play-by-play results."""
    games = _game_results_from_pbp(pbp)
    if games.empty:
        return pd.DataFrame(columns=PROFILE_COLUMNS)

    home_rows = games[["home_team", "home_score", "away_score"]].rename(
        columns={
            "home_team": "team",
            "home_score": "points_for",
            "away_score": "points_against",
        }
    )
    away_rows = games[["away_team", "away_score", "home_score"]].rename(
        columns={
            "away_team": "team",
            "away_score": "points_for",
            "home_score": "points_against",
        }
    )
    long = pd.concat([home_rows, away_rows], ignore_index=True)
    profiles = (
        long.groupby("team", as_index=False)
        .agg(
            games=("points_for", "count"),
            points_for_mean=("points_for", "mean"),
            points_for_std=("points_for", "std"),
            points_against_mean=("points_against", "mean"),
            points_against_std=("points_against", "std"),
        )
        .fillna(LEAGUE_SCORING_DEFAULTS)
    )
    profiles["points_for_std"] = profiles["points_for_std"].fillna(
        LEAGUE_SCORING_DEFAULTS["points_for_std"]
    )
    profiles["points_against_std"] = profiles["points_against_std"].fillna(
        LEAGUE_SCORING_DEFAULTS["points_against_std"]
    )
    return profiles


def _profile_row(profiles: pd.DataFrame, team: str) -> pd.Series:
    hit = profiles[profiles["team"] == team]
    if hit.empty:
        return pd.Series({"team": team, **LEAGUE_SCORING_DEFAULTS, "games": 0})
    return hit.iloc[0]


def expected_matchup_scores(
    home_team: str,
    away_team: str,
    profiles: pd.DataFrame,
    *,
    home_field_advantage: float = DEFAULT_HOME_FIELD_ADVANTAGE,
) -> tuple[float, float, float, float]:
    """Return expected home/away points and per-team simulation std dev."""
    home = _profile_row(profiles, home_team)
    away = _profile_row(profiles, away_team)

    home_mu = (home["points_for_mean"] + away["points_against_mean"]) / 2
    home_mu += home_field_advantage
    away_mu = (away["points_for_mean"] + home["points_against_mean"]) / 2

    home_std = float(
        np.nanmean([home["points_for_std"], away["points_against_std"]])
    )
    away_std = float(
        np.nanmean([away["points_for_std"], home["points_against_std"]])
    )
    return home_mu, away_mu, home_std, away_std


def calibrate_expected_scores_to_market(
    home_mu: float,
    away_mu: float,
    *,
    home_spread: float | None,
    total_line: float | None,
    market_blend: float = DEFAULT_MARKET_BLEND,
) -> tuple[float, float]:
    """Blend model expectations with market-implied scores."""
    if home_spread is None and total_line is None:
        return home_mu, away_mu

    model_total = home_mu + away_mu
    model_margin = home_mu - away_mu

    market_margin = -home_spread if home_spread is not None else model_margin
    market_total = total_line if total_line is not None else model_total
    market_home = (market_total + market_margin) / 2
    market_away = (market_total - market_margin) / 2

    weight = min(max(market_blend, 0.0), 1.0)
    home_blend = (1 - weight) * home_mu + weight * market_home
    away_blend = (1 - weight) * away_mu + weight * market_away
    return home_blend, away_blend


def simulate_game_outcomes(
    home_mu: float,
    away_mu: float,
    home_std: float,
    away_std: float,
    *,
    home_spread: float | None,
    away_spread: float | None,
    total_line: float | None,
    config: SimulationConfig | None = None,
) -> dict[str, float]:
    """Run Monte Carlo simulations and return cover/over probabilities."""
    cfg = config or SimulationConfig()
    rng = np.random.default_rng(cfg.random_seed)

    home_std = max(home_std, 6.0)
    away_std = max(away_std, 6.0)

    home_scores = rng.normal(home_mu, home_std, cfg.n_simulations).clip(min=0)
    away_scores = rng.normal(away_mu, away_std, cfg.n_simulations).clip(min=0)

    result: dict[str, float] = {
        "proj_home_score": float(home_mu),
        "proj_away_score": float(away_mu),
        "proj_total": float(home_mu + away_mu),
        "n_simulations": float(cfg.n_simulations),
    }

    if away_spread is not None and home_spread is not None:
        away_covers = away_scores + away_spread > home_scores
        home_covers = home_scores + home_spread > away_scores
        result["away_cover_pct"] = float(away_covers.mean())
        result["home_cover_pct"] = float(home_covers.mean())

    if total_line is not None:
        totals = home_scores + away_scores
        result["over_pct"] = float((totals > total_line).mean())
        result["under_pct"] = float((totals < total_line).mean())

    return result


def _pick_side(
    away_abbr: str,
    home_abbr: str,
    away_cover_pct: float | None,
    home_cover_pct: float | None,
    threshold: float,
) -> tuple[str | None, float | None, str | None]:
    if away_cover_pct is None or home_cover_pct is None:
        return None, None, None

    if away_cover_pct >= threshold and away_cover_pct > home_cover_pct:
        return away_abbr, away_cover_pct, "away"
    if home_cover_pct >= threshold and home_cover_pct > away_cover_pct:
        return home_abbr, home_cover_pct, "home"
    if away_cover_pct > home_cover_pct:
        return away_abbr, away_cover_pct, "away"
    return home_abbr, home_cover_pct, "home"


def _pick_total(
    over_pct: float | None,
    under_pct: float | None,
    threshold: float,
) -> tuple[str | None, float | None]:
    if over_pct is None or under_pct is None:
        return None, None
    if over_pct >= threshold and over_pct > under_pct:
        return "OVER", over_pct
    if under_pct >= threshold and under_pct > over_pct:
        return "UNDER", under_pct
    if over_pct >= under_pct:
        return "OVER", over_pct
    return "UNDER", under_pct


def simulate_weekly_picks(
    odds_games: pd.DataFrame,
    profiles: pd.DataFrame,
    *,
    week: int,
    schedule: pd.DataFrame | None = None,
    config: SimulationConfig | None = None,
) -> pd.DataFrame:
    """Simulate every odds row in a week and return spread/total recommendations."""
    cfg = config or SimulationConfig()
    if odds_games.empty:
        return pd.DataFrame()

    games = odds_games.copy()
    if "week" in games.columns:
        games = games[games["week"] == week]
    if games.empty:
        return pd.DataFrame()

    if schedule is not None and {"game_id", "home_score", "away_score"}.issubset(
        schedule.columns
    ):
        unplayed = schedule[schedule["home_score"].isna() & schedule["away_score"].isna()]
        games = games.merge(
            unplayed[["game_id"]],
            on="game_id",
            how="inner",
        )

    rows: list[dict] = []
    for game in games.itertuples(index=False):
        home_abbr = getattr(game, "home_abbr", None) or getattr(game, "home_team", None)
        away_abbr = getattr(game, "away_abbr", None) or getattr(game, "away_team", None)
        if not home_abbr or not away_abbr:
            continue

        home_mu, away_mu, home_std, away_std = expected_matchup_scores(
            str(home_abbr),
            str(away_abbr),
            profiles,
            home_field_advantage=cfg.home_field_advantage,
        )
        home_mu, away_mu = calibrate_expected_scores_to_market(
            home_mu,
            away_mu,
            home_spread=_safe_float(getattr(game, "home_spread", None)),
            total_line=_safe_float(getattr(game, "total_line", None)),
            market_blend=cfg.market_blend,
        )
        sim = simulate_game_outcomes(
            home_mu,
            away_mu,
            home_std,
            away_std,
            home_spread=_safe_float(getattr(game, "home_spread", None)),
            away_spread=_safe_float(getattr(game, "away_spread", None)),
            total_line=_safe_float(getattr(game, "total_line", None)),
            config=cfg,
        )

        spread_pick, spread_conf, spread_side = _pick_side(
            str(away_abbr),
            str(home_abbr),
            sim.get("away_cover_pct"),
            sim.get("home_cover_pct"),
            cfg.pick_threshold,
        )
        total_pick, total_conf = _pick_total(
            sim.get("over_pct"),
            sim.get("under_pct"),
            cfg.pick_threshold,
        )

        rows.append(
            {
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
                "proj_away_score": round(sim["proj_away_score"], 2),
                "proj_home_score": round(sim["proj_home_score"], 2),
                "proj_total": round(sim["proj_total"], 2),
                "away_cover_pct": _round_pct(sim.get("away_cover_pct")),
                "home_cover_pct": _round_pct(sim.get("home_cover_pct")),
                "over_pct": _round_pct(sim.get("over_pct")),
                "under_pct": _round_pct(sim.get("under_pct")),
                "spread_pick": spread_pick,
                "spread_side": spread_side,
                "spread_confidence": _round_pct(spread_conf),
                "total_pick": total_pick,
                "total_confidence": _round_pct(total_conf),
                "n_simulations": int(cfg.n_simulations),
            }
        )

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    return result.sort_values(
        ["gameday", "kickoff_et", "game_id"],
        na_position="last",
    ).reset_index(drop=True)


def infer_latest_completed_week(
    schedule: pd.DataFrame,
    *,
    season: int | None = None,
    game_types: tuple[str, ...] | list[str] = GAME_TYPES_REG_PLAYOFF,
) -> int | None:
    """Pick the latest week where every game has final scores."""
    if schedule.empty or "week" not in schedule.columns:
        return None

    sched = filter_schedule_game_types(schedule, game_types=game_types)
    if season is not None and "season" in sched.columns:
        sched = sched[sched["season"] == season]
    if not {"home_score", "away_score"}.issubset(sched.columns):
        return None

    completed_weeks: list[int] = []
    for week, games in sched.groupby("week"):
        if games["home_score"].notna().all() and games["away_score"].notna().all():
            completed_weeks.append(int(week))
    if not completed_weeks:
        return None
    return max(completed_weeks)


def infer_next_week(
    schedule: pd.DataFrame,
    *,
    season: int | None = None,
    game_types: tuple[str, ...] | list[str] = GAME_TYPES_REG_PLAYOFF,
) -> int | None:
    """Pick the earliest week without final scores."""
    if schedule.empty or "week" not in schedule.columns:
        return None

    sched = filter_schedule_game_types(schedule, game_types=game_types)
    if season is not None and "season" in sched.columns:
        sched = sched[sched["season"] == season]

    if {"home_score", "away_score"}.issubset(sched.columns):
        unplayed = sched[sched["home_score"].isna() & sched["away_score"].isna()]
    else:
        unplayed = sched

    if unplayed.empty:
        return None
    return int(unplayed["week"].min())


def _safe_float(value) -> float | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)


def _round_pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def new_prediction_run_id() -> str:
    return str(uuid4())


def new_grading_run_id() -> str:
    return str(uuid4())


def prepare_prediction_log(
    picks: pd.DataFrame,
    *,
    season: int,
    pbp_season: int,
    prediction_run_id: str,
    predicted_at: datetime | None = None,
    mlflow_run_id: str | None = None,
    config: SimulationConfig | None = None,
) -> pd.DataFrame:
    """Attach run metadata so predictions can be stored and graded later."""
    if picks.empty:
        return pd.DataFrame()

    cfg = config or SimulationConfig()
    stamped = predicted_at or datetime.now(timezone.utc)
    logged = picks.copy()
    logged["prediction_run_id"] = prediction_run_id
    logged["prediction_id"] = logged["game_id"].map(
        lambda game_id: f"{prediction_run_id}:{game_id}"
    )
    logged["season"] = season
    logged["pbp_season"] = pbp_season
    logged["predicted_at"] = stamped.isoformat()
    logged["mlflow_run_id"] = mlflow_run_id
    logged["market_blend"] = cfg.market_blend
    logged["pick_threshold"] = cfg.pick_threshold
    logged["home_field_advantage"] = cfg.home_field_advantage
    logged["random_seed"] = cfg.random_seed
    logged["n_simulations"] = cfg.n_simulations
    return logged.reset_index(drop=True)


def resolve_spread_result(
    away_score: float,
    home_score: float,
    *,
    away_spread: float,
    home_spread: float,
) -> str:
    """Return which side covered ATS: away, home, or push."""
    away_covers = away_score + away_spread > home_score
    home_covers = home_score + home_spread > away_score
    if away_covers and not home_covers:
        return "away"
    if home_covers and not away_covers:
        return "home"
    return "push"


def resolve_total_result(actual_total: float, total_line: float) -> str:
    """Return over, under, or push against the closing total."""
    if actual_total > total_line:
        return "over"
    if actual_total < total_line:
        return "under"
    return "push"


def _spread_pick_correct(
    spread_pick: str | None,
    spread_result: str,
    *,
    away_abbr: str,
    home_abbr: str,
) -> bool | None:
    if spread_result == "push" or not spread_pick:
        return None
    if spread_result == "away":
        return spread_pick == away_abbr
    return spread_pick == home_abbr


def _total_pick_correct(total_pick: str | None, total_result: str) -> bool | None:
    if total_result == "push" or not total_pick:
        return None
    return total_pick.upper() == total_result.upper()


GRADE_LINE_COLS = ("away_spread", "home_spread", "total_line")
_GRADE_RESULT_COLS = (
    "game_id",
    "home_score",
    "away_score",
    "home_team",
    "away_team",
    "game_type",
    "gameday",
    *GRADE_LINE_COLS,
)


def grade_predictions(
    predictions: pd.DataFrame,
    schedule: pd.DataFrame,
) -> pd.DataFrame:
    """Join predictions to final scores and compute ATS/total accuracy fields."""
    if predictions.empty:
        return pd.DataFrame()

    required = {"game_id", "home_score", "away_score"}
    if not required.issubset(schedule.columns):
        return pd.DataFrame()

    result_cols = [col for col in _GRADE_RESULT_COLS if col in schedule.columns]
    results = schedule[result_cols].dropna(subset=["home_score", "away_score"])
    preds = predictions.drop(
        columns=[col for col in GRADE_LINE_COLS if col in predictions.columns]
    )
    merged = preds.merge(results, on="game_id", how="inner")
    if merged.empty:
        return pd.DataFrame()

    graded_rows: list[dict[str, Any]] = []
    graded_at = datetime.now(timezone.utc).isoformat()

    for row in merged.itertuples(index=False):
        away_score = float(row.away_score)
        home_score = float(row.home_score)
        actual_total = away_score + home_score
        away_spread = _safe_float(getattr(row, "away_spread", None))
        home_spread = _safe_float(getattr(row, "home_spread", None))
        total_line = _safe_float(getattr(row, "total_line", None))

        spread_result = None
        total_result = None
        spread_correct = None
        total_correct = None

        if away_spread is not None and home_spread is not None:
            spread_result = resolve_spread_result(
                away_score,
                home_score,
                away_spread=away_spread,
                home_spread=home_spread,
            )
            spread_correct = _spread_pick_correct(
                getattr(row, "spread_pick", None),
                spread_result,
                away_abbr=str(row.away_abbr),
                home_abbr=str(row.home_abbr),
            )

        if total_line is not None:
            total_result = resolve_total_result(actual_total, total_line)
            total_correct = _total_pick_correct(
                getattr(row, "total_pick", None),
                total_result,
            )

        if away_score > home_score:
            actual_winner = str(row.away_abbr)
        elif home_score > away_score:
            actual_winner = str(row.home_abbr)
        else:
            actual_winner = "TIE"

        graded_rows.append(
            {
                "grade_id": str(uuid4()),
                "prediction_id": getattr(row, "prediction_id", None),
                "prediction_run_id": getattr(row, "prediction_run_id", None),
                "mlflow_run_id": getattr(row, "mlflow_run_id", None),
                "season": getattr(row, "season", None),
                "week": getattr(row, "week", None),
                "game_type": getattr(row, "game_type", None),
                "gameday": getattr(row, "gameday", None),
                "game_id": row.game_id,
                "away_abbr": row.away_abbr,
                "home_abbr": row.home_abbr,
                "spread_pick": getattr(row, "spread_pick", None),
                "total_pick": getattr(row, "total_pick", None),
                "spread_confidence": getattr(row, "spread_confidence", None),
                "total_confidence": getattr(row, "total_confidence", None),
                "away_spread": away_spread,
                "home_spread": home_spread,
                "total_line": total_line,
                "proj_away_score": getattr(row, "proj_away_score", None),
                "proj_home_score": getattr(row, "proj_home_score", None),
                "proj_total": getattr(row, "proj_total", None),
                "actual_away_score": away_score,
                "actual_home_score": home_score,
                "actual_total": actual_total,
                "actual_winner": actual_winner,
                "actual_spread_result": spread_result,
                "actual_total_result": total_result,
                "spread_correct": spread_correct,
                "total_correct": total_correct,
                "spread_push": spread_result == "push" if spread_result else None,
                "total_push": total_result == "push" if total_result else None,
                "away_score_error": _round_score(
                    getattr(row, "proj_away_score", None), away_score
                ),
                "home_score_error": _round_score(
                    getattr(row, "proj_home_score", None), home_score
                ),
                "total_error": _round_score(getattr(row, "proj_total", None), actual_total),
                "graded_at": graded_at,
            }
        )

    return pd.DataFrame(graded_rows)


def filter_ungraded_predictions(
    predictions: pd.DataFrame,
    grades: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Drop prediction rows that already have a stored grade."""
    if predictions.empty:
        return predictions

    if grades is not None and not grades.empty and "prediction_id" in grades.columns:
        graded_ids = set(grades["prediction_id"].dropna())
        if "prediction_id" in predictions.columns:
            return predictions[~predictions["prediction_id"].isin(graded_ids)].copy()

    return predictions


def select_latest_prediction_run(
    predictions: pd.DataFrame,
    *,
    season: int,
    week: int,
) -> str | None:
    """Return the most recent prediction_run_id for a season/week."""
    if predictions.empty:
        return None

    subset = predictions[
        (predictions["season"] == season) & (predictions["week"] == week)
    ].copy()
    if subset.empty:
        return None

    subset = subset.sort_values("predicted_at")
    return str(subset.iloc[-1]["prediction_run_id"])


def select_latest_predictions_per_game(predictions: pd.DataFrame) -> pd.DataFrame:
    """Keep the most recent prediction row per game_id."""
    if predictions.empty or "game_id" not in predictions.columns:
        return predictions.copy()
    if "predicted_at" not in predictions.columns:
        return predictions.drop_duplicates(subset=["game_id"], keep="last")
    return (
        predictions.sort_values("predicted_at")
        .drop_duplicates(subset=["game_id"], keep="last")
        .reset_index(drop=True)
    )


def summarize_prediction_accuracy(graded: pd.DataFrame) -> dict[str, float]:
    """Aggregate accuracy metrics for MLflow logging and dashboards."""
    if graded.empty:
        return {}

    spread_graded = graded[graded["spread_push"] != True]  # noqa: E712
    total_graded = graded[graded["total_push"] != True]  # noqa: E712

    metrics: dict[str, float] = {
        "games_graded": float(len(graded)),
    }

    if not spread_graded.empty and spread_graded["spread_correct"].notna().any():
        spread_hits = spread_graded["spread_correct"].dropna()
        metrics["spread_games"] = float(len(spread_hits))
        metrics["spread_accuracy"] = float(spread_hits.mean())
        metrics["spread_hits"] = float(spread_hits.sum())

    if not total_graded.empty and total_graded["total_correct"].notna().any():
        total_hits = total_graded["total_correct"].dropna()
        metrics["total_games"] = float(len(total_hits))
        metrics["total_accuracy"] = float(total_hits.mean())
        metrics["total_hits"] = float(total_hits.sum())

    if "spread_confidence" in graded.columns:
        high_conf = spread_graded[
            spread_graded["spread_confidence"].notna()
            & (spread_graded["spread_confidence"] >= DEFAULT_PICK_THRESHOLD)
        ]
        if not high_conf.empty and high_conf["spread_correct"].notna().any():
            hits = high_conf["spread_correct"].dropna()
            metrics["spread_high_conf_games"] = float(len(hits))
            metrics["spread_high_conf_accuracy"] = float(hits.mean())

    if "total_confidence" in graded.columns:
        high_conf = total_graded[
            total_graded["total_confidence"].notna()
            & (total_graded["total_confidence"] >= DEFAULT_PICK_THRESHOLD)
        ]
        if not high_conf.empty and high_conf["total_correct"].notna().any():
            hits = high_conf["total_correct"].dropna()
            metrics["total_high_conf_games"] = float(len(hits))
            metrics["total_high_conf_accuracy"] = float(hits.mean())

    if "away_score_error" in graded.columns and graded["away_score_error"].notna().any():
        metrics["mae_away_score"] = float(graded["away_score_error"].abs().mean())
    if "home_score_error" in graded.columns and graded["home_score_error"].notna().any():
        metrics["mae_home_score"] = float(graded["home_score_error"].abs().mean())
    if "total_error" in graded.columns and graded["total_error"].notna().any():
        metrics["mae_total"] = float(graded["total_error"].abs().mean())

    return metrics


def _round_score(projected: float | None, actual: float) -> float | None:
    if projected is None:
        return None
    return round(float(projected) - actual, 2)