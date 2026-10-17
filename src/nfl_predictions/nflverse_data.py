"""Download reference datasets from nflverse."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

NFLVERSE_GAMES_URL = "https://github.com/nflverse/nfldata/raw/master/data/games.csv"
NFLVERSE_TEAMS_URL = "https://github.com/nflverse/nfldata/raw/master/data/teams.csv"
NFLVERSE_PBP_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
)
NFLVERSE_ROSTER_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{season}.csv"
)

GAME_TYPES_REG_PLAYOFF = ("REG", "WC", "DIV", "CON", "SB")
ET = ZoneInfo("America/New_York")


class PbpNotAvailableError(FileNotFoundError):
    """Raised when nflverse has not published PBP for a season yet."""


def parse_season_list(value: str) -> list[int]:
    """Parse comma-separated season years (e.g. '2024,2025')."""
    seasons: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if part:
            seasons.append(int(part))
    return seasons


def fetch_teams() -> pd.DataFrame:
    """Load nflverse team reference rows."""
    return pd.read_csv(NFLVERSE_TEAMS_URL)


def fetch_play_by_play(
    season: int,
    *,
    regular_season_only: bool = False,
) -> pd.DataFrame:
    """Load play-by-play for a season.

    Preseason (PRE) is never included. Playoff plays are retained unless
    ``regular_season_only`` is True; at load time, join ``schedules.games`` on
    ``game_id`` and filter ``game_type`` with ``GAME_TYPES_REG_PLAYOFF``.
    """
    url = NFLVERSE_PBP_URL.format(season=season)
    try:
        pbp = pd.read_parquet(url)
    except Exception as exc:
        if _is_missing_pbp_release(exc):
            raise PbpNotAvailableError(
                f"nflverse play-by-play not available for season {season}"
            ) from exc
        raise

    if "season_type" in pbp.columns:
        pbp = pbp[pbp["season_type"] != "PRE"].copy()

    if regular_season_only and "season_type" in pbp.columns:
        pbp = pbp[pbp["season_type"] == "REG"].copy()

    return pbp


def _is_missing_pbp_release(exc: Exception) -> bool:
    message = str(exc).lower()
    return "404" in message or "not found" in message


def get_elapsed_weeks(
    schedule: pd.DataFrame,
    season: int,
    *,
    as_of: date | datetime | None = None,
    game_types: tuple[str, ...] | list[str] = ("REG",),
) -> list[int]:
    """Return weeks fully elapsed as of the given date."""
    if as_of is None:
        as_of_date = datetime.now(ET).date()
    elif isinstance(as_of, datetime):
        as_of_date = as_of.astimezone(ET).date()
    else:
        as_of_date = as_of

    reg = schedule[
        (schedule["season"] == season) & (schedule["game_type"].isin(game_types))
    ].copy()
    if reg.empty:
        return []

    elapsed: list[int] = []
    score_cols = {"home_score", "away_score"}.issubset(reg.columns)
    season_has_scores = (
        score_cols and reg["home_score"].notna().any() and reg["away_score"].notna().any()
    )

    for week, games in reg.groupby("week"):
        game_days = pd.to_datetime(games["gameday"]).dt.date
        week_complete_by_date = game_days.max() < as_of_date

        if season_has_scores:
            week_complete = (
                games["home_score"].notna().all() and games["away_score"].notna().all()
            )
        else:
            week_complete = week_complete_by_date

        if week_complete:
            elapsed.append(int(week))

    return sorted(elapsed)


def fetch_play_by_play_for_elapsed_weeks(
    season: int,
    *,
    as_of: date | datetime | None = None,
    regular_season_only: bool = True,
    game_types: tuple[str, ...] | list[str] = ("REG",),
) -> tuple[pd.DataFrame, list[int]]:
    """Load current-season PBP limited to fully elapsed weeks."""
    schedule = fetch_season_schedule(season, game_types=game_types)
    elapsed_weeks = get_elapsed_weeks(schedule, season, as_of=as_of, game_types=game_types)
    if not elapsed_weeks:
        return pd.DataFrame(), []

    pbp = fetch_play_by_play(season, regular_season_only=regular_season_only)
    if pbp.empty:
        return pbp, elapsed_weeks

    filtered = pbp[
        (pbp["season"] == season) & (pbp["week"].isin(elapsed_weeks))
    ].copy()
    return filtered, elapsed_weeks


def fetch_rosters(season: int) -> pd.DataFrame:
    """Load season-level roster snapshot."""
    url = NFLVERSE_ROSTER_URL.format(season=season)
    return pd.read_csv(url)


def fetch_season_schedule(
    season: int,
    *,
    game_types: tuple[str, ...] | list[str] = GAME_TYPES_REG_PLAYOFF,
) -> pd.DataFrame:
    """Load schedule rows for a season."""
    schedule = pd.read_csv(NFLVERSE_GAMES_URL)
    filtered = schedule[schedule["season"] == season].copy()
    if game_types:
        filtered = filtered[filtered["game_type"].isin(game_types)]
    return filtered.reset_index(drop=True)


def fetch_schedules_for_seasons(
    seasons: list[int],
    *,
    game_types: tuple[str, ...] | list[str] = GAME_TYPES_REG_PLAYOFF,
) -> pd.DataFrame:
    """Load and concatenate schedule rows for multiple seasons."""
    frames = [fetch_season_schedule(season, game_types=game_types) for season in seasons]
    non_empty = [frame for frame in frames if not frame.empty]
    if not non_empty:
        return pd.DataFrame()
    return pd.concat(non_empty, ignore_index=True)


def merge_schedule_season(
    existing: pd.DataFrame,
    new: pd.DataFrame,
    season: int,
) -> pd.DataFrame:
    """Replace one season in a schedule table while preserving all other seasons."""
    if existing is None or existing.empty:
        merged = new.copy()
    else:
        kept = existing[existing["season"] != season]
        if kept.empty:
            merged = new.copy()
        elif new.empty:
            merged = kept.copy()
        else:
            aligned_new = new.copy()
            for col in kept.columns.intersection(aligned_new.columns):
                if pd.api.types.is_numeric_dtype(kept[col]) and not pd.api.types.is_numeric_dtype(
                    aligned_new[col]
                ):
                    aligned_new[col] = pd.to_numeric(aligned_new[col], errors="coerce")
            merged = pd.concat([kept, aligned_new], ignore_index=True)

    if "game_id" in merged.columns:
        merged = merged.drop_duplicates(subset=["game_id"], keep="last")
    return merged.reset_index(drop=True)


def get_loaded_weeks(pbp_df: pd.DataFrame, season: int) -> list[int]:
    """Return sorted list of distinct weeks already present for a given season."""
    if pbp_df is None or pbp_df.empty:
        return []
    mask = pbp_df["season"] == season if "season" in pbp_df.columns else pd.Series(False, index=pbp_df.index)
    weeks = pbp_df.loc[mask, "week"].dropna().astype(int).unique().tolist()
    return sorted(set(int(w) for w in weeks))