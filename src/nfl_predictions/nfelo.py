"""Fetch and apply nfelo power ratings (https://www.nfeloapp.com/nfl-power-ratings/)."""

from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd
import requests

NFELO_SNAPSHOT_URL = (
    "https://raw.githubusercontent.com/greerreNFL/nfelo/main/output_data/elo_snapshot.csv"
)
NFELO_GAMES_URL = (
    "https://raw.githubusercontent.com/greerreNFL/nfelo/main/output_data/nfelo_games.csv"
)
NFELO_SOURCE = "nfelo_github"

# nfelo uses legacy abbreviations in some rows (e.g. OAK for Raiders).
NFELO_TO_NFLVERSE: dict[str, str] = {
    "OAK": "LV",
    "STL": "LA",
    "SD": "LAC",
}

NFLVERSE_TO_NFELO: dict[str, str] = {value: key for key, value in NFELO_TO_NFLVERSE.items()}

DEFAULT_ELO_TO_MARGIN = 18.5
DEFAULT_LEAGUE_SCORING_AVG = 22.5

RATINGS_COLUMNS = [
    "team",
    "season",
    "week",
    "nfelo",
    "nfelo_base",
    "qb_adj",
    "pts_vs_avg",
]


def normalize_nfelo_team(team: str) -> str:
    """Map nfelo team codes to nflverse abbreviations."""
    code = str(team).strip().upper()
    return NFELO_TO_NFLVERSE.get(code, code)


def to_nfelo_team(team: str) -> str:
    """Map nflverse abbreviations to nfelo codes when they differ."""
    code = str(team).strip().upper()
    return NFLVERSE_TO_NFELO.get(code, code)


def fetch_nfelo_snapshot(*, timeout: float = 30.0) -> pd.DataFrame:
    """Download the latest team ratings snapshot from the nfelo GitHub repo."""
    response = requests.get(NFELO_SNAPSHOT_URL, timeout=timeout)
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text))
    if "Unnamed: 0" in frame.columns:
        frame = frame.drop(columns=["Unnamed: 0"])
    return normalize_nfelo_ratings(frame)


def fetch_nfelo_games(*, timeout: float = 120.0) -> pd.DataFrame:
    """Download per-game nfelo lines and pre-game ratings."""
    response = requests.get(NFELO_GAMES_URL, timeout=timeout)
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text))
    if "Unnamed: 0" in frame.columns:
        frame = frame.drop(columns=["Unnamed: 0"])
    return frame


def normalize_nfelo_ratings(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardize nfelo snapshot columns and team codes."""
    if frame.empty:
        return pd.DataFrame(columns=RATINGS_COLUMNS)

    ratings = frame.copy()
    ratings["team"] = ratings["team"].map(normalize_nfelo_team)
    for column in ("season", "week"):
        if column in ratings.columns:
            ratings[column] = pd.to_numeric(ratings[column], errors="coerce").astype("Int64")
    for column in ("nfelo", "nfelo_base", "qb_adj", "pts_vs_avg"):
        if column in ratings.columns:
            ratings[column] = pd.to_numeric(ratings[column], errors="coerce")
    keep = [column for column in RATINGS_COLUMNS if column in ratings.columns]
    return ratings[keep].dropna(subset=["team", "nfelo"]).reset_index(drop=True)


def select_nfelo_ratings(
    ratings: pd.DataFrame,
    *,
    season: int,
    week: int | None = None,
) -> pd.DataFrame:
    """Pick the best available nfelo snapshot for a target season/week."""
    if ratings.empty:
        return pd.DataFrame(columns=RATINGS_COLUMNS)

    season_rows = ratings[ratings["season"] == season].copy()
    if season_rows.empty:
        prior = ratings[ratings["season"] == season - 1].copy()
        if prior.empty:
            return pd.DataFrame(columns=RATINGS_COLUMNS)
        season_rows = prior[prior["week"] == prior["week"].max()]

    if week is not None and season_rows["week"].eq(week).any():
        season_rows = season_rows[season_rows["week"] == week]
    else:
        season_rows = season_rows[season_rows["week"] == season_rows["week"].max()]

    return season_rows.drop_duplicates(subset=["team"], keep="last").reset_index(drop=True)


def nfelo_ratings_lookup(ratings: pd.DataFrame) -> dict[str, float]:
    """Return team -> nfelo rating for fast simulation lookups."""
    if ratings.empty:
        return {}
    return {
        str(row.team): float(row.nfelo)
        for row in ratings.itertuples(index=False)
        if pd.notna(row.nfelo)
    }


def nfelo_games_lookup(games: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Return game_id -> nfelo game fields used during simulation."""
    if games.empty or "game_id" not in games.columns:
        return {}

    lookup: dict[str, dict[str, Any]] = {}
    for row in games.itertuples(index=False):
        game_id = getattr(row, "game_id", None)
        if not game_id:
            continue
        lookup[str(game_id)] = {
            "nfelo_home_line_close": _safe_float(
                getattr(row, "nfelo_home_line_close", None)
            ),
            "starting_nfelo_home": _safe_float(getattr(row, "starting_nfelo_home", None)),
            "starting_nfelo_away": _safe_float(getattr(row, "starting_nfelo_away", None)),
            "nfelo_home_probability_close": _safe_float(
                getattr(row, "nfelo_home_probability_close", None)
            ),
        }
    return lookup


def nfelo_implied_margin(
    home_nfelo: float,
    away_nfelo: float,
    *,
    elo_to_margin: float = DEFAULT_ELO_TO_MARGIN,
) -> float:
    """Convert nfelo ratings to an expected home scoring margin."""
    return (home_nfelo - away_nfelo) / elo_to_margin


def blend_nfelo_margin(
    home_mu: float,
    away_mu: float,
    *,
    home_nfelo: float | None,
    away_nfelo: float | None,
    nfelo_blend: float,
    elo_to_margin: float = DEFAULT_ELO_TO_MARGIN,
) -> tuple[float, float]:
    """Blend PBP expected scores toward nfelo-implied margin."""
    if nfelo_blend <= 0 or home_nfelo is None or away_nfelo is None:
        return home_mu, away_mu

    pbp_margin = home_mu - away_mu
    nfelo_margin = nfelo_implied_margin(
        home_nfelo,
        away_nfelo,
        elo_to_margin=elo_to_margin,
    )
    weight = min(max(nfelo_blend, 0.0), 1.0)
    margin = (1 - weight) * pbp_margin + weight * nfelo_margin
    center = (home_mu + away_mu) / 2
    return center + margin / 2, center - margin / 2


def scores_from_nfelo_spread(
    home_spread: float,
    *,
    total_line: float | None = None,
    league_avg: float = DEFAULT_LEAGUE_SCORING_AVG,
) -> tuple[float, float]:
    """Convert nfelo home spread (negative = home favored) into expected scores."""
    total = total_line if total_line is not None else 2 * league_avg
    margin = -home_spread
    return (total + margin) / 2, (total - margin) / 2


def blend_nfelo_game_line(
    home_mu: float,
    away_mu: float,
    *,
    nfelo_home_line: float | None,
    total_line: float | None,
    nfelo_blend: float,
) -> tuple[float, float]:
    """Blend PBP scores toward nfelo's projected spread for a specific game."""
    if nfelo_blend <= 0 or nfelo_home_line is None:
        return home_mu, away_mu

    nfelo_home_mu, nfelo_away_mu = scores_from_nfelo_spread(
        nfelo_home_line,
        total_line=total_line,
    )
    weight = min(max(nfelo_blend, 0.0), 1.0)
    home_blend = (1 - weight) * home_mu + weight * nfelo_home_mu
    away_blend = (1 - weight) * away_mu + weight * nfelo_away_mu
    return home_blend, away_blend


def apply_nfelo_to_matchup_scores(
    home_mu: float,
    away_mu: float,
    *,
    home_team: str,
    away_team: str,
    nfelo_lookup: dict[str, float],
    nfelo_game: dict[str, Any] | None,
    nfelo_blend: float,
    total_line: float | None = None,
) -> tuple[float, float, float | None, float | None, float | None]:
    """Apply nfelo team or game adjustments before market calibration."""
    if nfelo_blend <= 0:
        return home_mu, away_mu, None, None, None

    home_rating = nfelo_lookup.get(home_team)
    away_rating = nfelo_lookup.get(away_team)
    game_line = None
    if nfelo_game:
        game_line = nfelo_game.get("nfelo_home_line_close")
        if home_rating is None:
            home_rating = nfelo_game.get("starting_nfelo_home")
        if away_rating is None:
            away_rating = nfelo_game.get("starting_nfelo_away")

    if game_line is not None:
        home_mu, away_mu = blend_nfelo_game_line(
            home_mu,
            away_mu,
            nfelo_home_line=game_line,
            total_line=total_line,
            nfelo_blend=nfelo_blend,
        )
    elif home_rating is not None and away_rating is not None:
        home_mu, away_mu = blend_nfelo_margin(
            home_mu,
            away_mu,
            home_nfelo=home_rating,
            away_nfelo=away_rating,
            nfelo_blend=nfelo_blend,
        )
    else:
        home_rating = away_rating = game_line = None

    return home_mu, away_mu, home_rating, away_rating, game_line


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)