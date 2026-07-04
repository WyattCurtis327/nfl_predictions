"""Fetch and transform live NFL odds from The Odds API."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from nfl_predictions.odds import (
    GAME_ODDS_COLUMNS,
    GAME_ODDS_KEY,
    ODDS_INGEST_GAPS_COLUMNS,
    extract_odds_lines,
)
from nfl_predictions.teams import to_abbr

ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ODDS_API_SOURCE = "odds_api"
DEFAULT_MARKETS = "h2h,spreads,totals"
DEFAULT_REGIONS = "us"
ET = ZoneInfo("America/New_York")


class OddsApiError(RuntimeError):
    pass


def fetch_nfl_odds(
    api_key: str | None = None,
    *,
    regions: str = DEFAULT_REGIONS,
    markets: str = DEFAULT_MARKETS,
    odds_format: str = "american",
    timeout: int = 30,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Return upcoming NFL odds and response headers."""
    key = (api_key or os.environ.get("ODDS_API_KEY") or os.environ.get("odds_api_key") or "").strip()
    if not key:
        raise OddsApiError("Missing ODDS_API_KEY environment variable or api_key argument")

    url = f"{ODDS_API_BASE}/sports/americanfootball_nfl/odds"
    params = {
        "apiKey": key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": odds_format,
    }
    response = requests.get(url, params=params, timeout=timeout)
    if not response.ok:
        raise OddsApiError(f"Odds API request failed ({response.status_code}): {response.text}")

    headers = {
        "x-requests-remaining": response.headers.get("x-requests-remaining", ""),
        "x-requests-used": response.headers.get("x-requests-used", ""),
        "x-requests-last": response.headers.get("x-requests-last", ""),
    }
    return response.json(), headers


def kickoff_et_date(commence_time: str) -> str:
    kickoff = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    return kickoff.astimezone(ET).date().isoformat()


def kickoff_et_datetime(commence_time: str) -> str:
    kickoff = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    return kickoff.astimezone(ET).strftime("%Y-%m-%d %H:%M")


def match_game_ids(
    odds_games: list[dict[str, Any]],
    schedule: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    """Map Odds API event id to nflverse game metadata."""
    lookup: dict[str, dict[str, Any]] = {}

    for game in odds_games:
        away_abbr = to_abbr(game["away_team"])
        home_abbr = to_abbr(game["home_team"])
        gameday = kickoff_et_date(game["commence_time"])

        match = schedule[
            (schedule["away_team"] == away_abbr)
            & (schedule["home_team"] == home_abbr)
            & (schedule["gameday"] == gameday)
        ]
        if match.empty:
            match = schedule[
                (schedule["away_team"] == away_abbr) & (schedule["home_team"] == home_abbr)
            ]

        if match.empty:
            lookup[game["id"]] = {
                "game_id": None,
                "season": None,
                "week": None,
                "game_type": None,
                "away_abbr": away_abbr,
                "home_abbr": home_abbr,
                "gameday": gameday,
            }
            continue

        row = match.iloc[0]
        lookup[game["id"]] = {
            "game_id": row["game_id"],
            "season": int(row["season"]) if pd.notna(row.get("season")) else None,
            "week": int(row["week"]) if pd.notna(row.get("week")) else None,
            "game_type": row.get("game_type"),
            "away_abbr": away_abbr,
            "home_abbr": home_abbr,
            "gameday": gameday,
        }

    return lookup


def to_game_odds_rows(
    odds_games: list[dict[str, Any]],
    schedule: pd.DataFrame,
    *,
    preferred_bookmaker: str = "draftkings",
    ingested_at: datetime | None = None,
) -> list[dict[str, Any]]:
    """Build one wide row per game using a preferred bookmaker."""
    ingested = ingested_at or datetime.now(timezone.utc)
    game_lookup = match_game_ids(odds_games, schedule)
    rows: list[dict[str, Any]] = []

    for game in odds_games:
        meta = game_lookup[game["id"]]
        if not meta.get("game_id"):
            continue

        bookmaker = next(
            (b for b in game.get("bookmakers", []) if b["key"] == preferred_bookmaker),
            game["bookmakers"][0] if game.get("bookmakers") else None,
        )
        if not bookmaker:
            continue

        h2h = next((m for m in bookmaker["markets"] if m["key"] == "h2h"), None)
        spreads = next((m for m in bookmaker["markets"] if m["key"] == "spreads"), None)
        totals = next((m for m in bookmaker["markets"] if m["key"] == "totals"), None)

        def outcome(market, team_name: str):
            if not market:
                return None, None
            hit = next((o for o in market["outcomes"] if o["name"] == team_name), None)
            if not hit:
                return None, None
            return hit.get("point"), hit.get("price")

        away_spread, away_spread_odds = outcome(spreads, game["away_team"])
        home_spread, home_spread_odds = outcome(spreads, game["home_team"])
        _, away_ml = outcome(h2h, game["away_team"])
        _, home_ml = outcome(h2h, game["home_team"])
        over = next((o for o in (totals or {}).get("outcomes", []) if o["name"] == "Over"), None)
        under = next((o for o in (totals or {}).get("outcomes", []) if o["name"] == "Under"), None)

        rows.append(
            {
                "game_id": meta["game_id"],
                "season": meta["season"],
                "week": meta["week"],
                "game_type": meta["game_type"],
                "gameday": meta["gameday"],
                "home_team": meta["home_abbr"],
                "away_team": meta["away_abbr"],
                "spread_line": home_spread,
                "total_line": over.get("point") if over else None,
                "away_moneyline": away_ml,
                "home_moneyline": home_ml,
                "away_spread_odds": away_spread_odds,
                "home_spread_odds": home_spread_odds,
                "under_odds": under.get("price") if under else None,
                "over_odds": over.get("price") if over else None,
                "source": ODDS_API_SOURCE,
                "bookmaker": bookmaker["key"],
                "ingested_at": ingested,
            }
        )

    return rows


def _game_odds_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=GAME_ODDS_COLUMNS)
    frame = pd.DataFrame(rows)
    available = [col for col in GAME_ODDS_COLUMNS if col in frame.columns]
    return frame[available].drop_duplicates(subset=GAME_ODDS_KEY, keep="last").reset_index(drop=True)


def find_api_ingest_gaps(
    schedule_subset: pd.DataFrame,
    game_odds: pd.DataFrame,
) -> pd.DataFrame:
    """Scheduled games missing from an Odds API ingest."""
    if schedule_subset.empty:
        return pd.DataFrame(columns=ODDS_INGEST_GAPS_COLUMNS)

    scheduled_ids = set(schedule_subset["game_id"].astype(str))
    matched_ids = (
        set(game_odds["game_id"].astype(str)) if not game_odds.empty and "game_id" in game_odds.columns else set()
    )
    missing_ids = scheduled_ids - matched_ids
    if not missing_ids:
        return pd.DataFrame(columns=ODDS_INGEST_GAPS_COLUMNS)

    missing = schedule_subset[schedule_subset["game_id"].astype(str).isin(missing_ids)].copy()
    id_cols = [
        col
        for col in ["game_id", "season", "week", "game_type", "gameday", "home_team", "away_team"]
        if col in missing.columns
    ]
    result = missing[id_cols].copy()
    result["gap_reason"] = "no_odds_api_match"
    available = [col for col in ODDS_INGEST_GAPS_COLUMNS if col in result.columns]
    return result[available].drop_duplicates(subset=["game_id"], keep="last").reset_index(drop=True)


def assess_schedule_match_rate(
    schedule_subset: pd.DataFrame,
    game_odds: pd.DataFrame,
    *,
    min_rate: float = 0.9,
) -> dict[str, Any]:
    """Return match stats for scheduled games covered by Odds API ingest."""
    total = len(schedule_subset)
    if total == 0:
        return {
            "total_games": 0,
            "matched_games": 0,
            "unmatched_games": 0,
            "match_rate": 1.0,
            "min_rate": min_rate,
            "passed": True,
        }

    scheduled_ids = set(schedule_subset["game_id"].astype(str))
    matched_ids = (
        set(game_odds["game_id"].astype(str)) if not game_odds.empty and "game_id" in game_odds.columns else set()
    )
    matched = len(scheduled_ids & matched_ids)
    rate = matched / total
    return {
        "total_games": total,
        "matched_games": matched,
        "unmatched_games": total - matched,
        "match_rate": round(rate, 4),
        "min_rate": min_rate,
        "passed": rate >= min_rate,
    }


def build_odds_from_api(
    odds_games: list[dict[str, Any]],
    schedule: pd.DataFrame,
    *,
    season: int | None = None,
    week: int | None = None,
    preferred_bookmaker: str = "draftkings",
    ingested_at: datetime | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return game odds, odds lines, latest snapshot, and ingest gaps from Odds API."""
    sched = schedule.copy()
    if season is not None and "season" in sched.columns:
        sched = sched[sched["season"] == season]
    if week is not None and "week" in sched.columns:
        sched = sched[sched["week"] == week]

    rows = to_game_odds_rows(
        odds_games,
        schedule,
        preferred_bookmaker=preferred_bookmaker,
        ingested_at=ingested_at,
    )
    game_odds = _game_odds_dataframe(rows)
    if not game_odds.empty and season is not None:
        game_odds = game_odds[game_odds["season"] == season]
    if not game_odds.empty and week is not None:
        game_odds = game_odds[game_odds["week"] == week]

    odds_lines = extract_odds_lines(game_odds)
    gaps = find_api_ingest_gaps(sched, game_odds)
    latest = game_odds.copy()
    return game_odds, odds_lines, latest, gaps