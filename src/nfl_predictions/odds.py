"""Extract historical closing odds embedded in nflverse schedule rows."""

from __future__ import annotations

import pandas as pd

from nfl_predictions.nflverse_data import GAME_TYPES_REG_PLAYOFF, NFLVERSE_GAMES_URL

NFLVERSE_SOURCE = "nflverse"
NFLVERSE_BOOKMAKER = "nflverse"

SCHEDULE_ODDS_COLUMNS = [
    "spread_line",
    "total_line",
    "away_moneyline",
    "home_moneyline",
    "away_spread_odds",
    "home_spread_odds",
    "under_odds",
    "over_odds",
]

GAME_ODDS_COLUMNS = [
    "game_id",
    "season",
    "week",
    "game_type",
    "gameday",
    "home_team",
    "away_team",
    "spread_line",
    "total_line",
    "away_moneyline",
    "home_moneyline",
    "away_spread_odds",
    "home_spread_odds",
    "under_odds",
    "over_odds",
    "source",
    "bookmaker",
]

ODDS_LINES_COLUMNS = [
    "game_id",
    "season",
    "week",
    "game_type",
    "market",
    "side",
    "line",
    "price",
    "source",
    "bookmaker",
]

ODDS_INGEST_GAPS_COLUMNS = [
    "game_id",
    "season",
    "week",
    "game_type",
    "gameday",
    "home_team",
    "away_team",
    "gap_reason",
]

GAME_KEY_COLUMNS = ["spread_line", "total_line", "away_moneyline", "home_moneyline"]
GAME_ODDS_KEY = ["game_id"]
ODDS_LINES_KEY = ["game_id", "market", "side"]
ODDS_GAPS_KEY = ["game_id"]


def _dedupe(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    available = [key for key in keys if key in frame.columns]
    if not available or frame.empty:
        return frame.reset_index(drop=True)
    return frame.drop_duplicates(subset=available, keep="last").reset_index(drop=True)


def _schedule_games(schedule: pd.DataFrame) -> pd.DataFrame:
    if schedule.empty:
        return schedule.copy()
    games = schedule.copy()
    if "game_id" in games.columns:
        games = _dedupe(games, ["game_id"])
    mask = games["game_type"].isin(GAME_TYPES_REG_PLAYOFF)
    return games.loc[mask].copy()


def _has_full_odds(frame: pd.DataFrame) -> pd.Series:
    available = [col for col in GAME_KEY_COLUMNS if col in frame.columns]
    if not available:
        return pd.Series(False, index=frame.index)
    return frame[available].notna().all(axis=1)


def extract_game_odds(schedule: pd.DataFrame) -> pd.DataFrame:
    """One row per scheduled game that has nflverse closing odds."""
    games = _schedule_games(schedule)
    if games.empty:
        return pd.DataFrame(columns=GAME_ODDS_COLUMNS)

    odds_cols = [col for col in SCHEDULE_ODDS_COLUMNS if col in games.columns]
    if not odds_cols:
        return pd.DataFrame(columns=GAME_ODDS_COLUMNS)

    with_odds = games.loc[_has_full_odds(games)].copy()
    if with_odds.empty:
        return pd.DataFrame(columns=GAME_ODDS_COLUMNS)

    id_cols = [
        col
        for col in ["game_id", "season", "week", "game_type", "gameday", "home_team", "away_team"]
        if col in with_odds.columns
    ]
    result = with_odds[id_cols + odds_cols].copy()
    result["source"] = NFLVERSE_SOURCE
    result["bookmaker"] = NFLVERSE_BOOKMAKER

    available = [col for col in GAME_ODDS_COLUMNS if col in result.columns]
    return _dedupe(result[available], GAME_ODDS_KEY)


def extract_odds_lines(game_odds: pd.DataFrame) -> pd.DataFrame:
    """Long-format market rows derived from wide nflverse game odds."""
    if game_odds.empty:
        return pd.DataFrame(columns=ODDS_LINES_COLUMNS)

    base_cols = [col for col in ["game_id", "season", "week", "game_type"] if col in game_odds.columns]
    rows: list[dict[str, object]] = []

    def add_row(
        row: pd.Series,
        *,
        market: str,
        side: str,
        line: object,
        price: object,
    ) -> None:
        if pd.isna(price):
            return
        entry = {col: row[col] for col in base_cols}
        entry.update(
            {
                "market": market,
                "side": side,
                "line": line,
                "price": price,
                "source": row.get("source", NFLVERSE_SOURCE),
                "bookmaker": row.get("bookmaker", NFLVERSE_BOOKMAKER),
            }
        )
        rows.append(entry)

    for _, row in game_odds.iterrows():
        add_row(row, market="spread", side="home", line=row.get("spread_line"), price=row.get("home_spread_odds"))
        add_row(row, market="spread", side="away", line=-row.get("spread_line") if pd.notna(row.get("spread_line")) else None, price=row.get("away_spread_odds"))
        add_row(row, market="total", side="over", line=row.get("total_line"), price=row.get("over_odds"))
        add_row(row, market="total", side="under", line=row.get("total_line"), price=row.get("under_odds"))
        add_row(row, market="moneyline", side="home", line=None, price=row.get("home_moneyline"))
        add_row(row, market="moneyline", side="away", line=None, price=row.get("away_moneyline"))

    if not rows:
        return pd.DataFrame(columns=ODDS_LINES_COLUMNS)

    result = pd.DataFrame(rows)
    available = [col for col in ODDS_LINES_COLUMNS if col in result.columns]
    return _dedupe(result[available], ODDS_LINES_KEY)


def _gap_reason(row: pd.Series) -> str:
    if not any(col in row.index for col in SCHEDULE_ODDS_COLUMNS):
        return "no_odds_columns"
    if not row[[col for col in SCHEDULE_ODDS_COLUMNS if col in row.index]].notna().any():
        return "no_odds"
    if not _has_full_odds(pd.DataFrame([row])).iloc[0]:
        return "partial_odds"
    return "unknown"


def find_odds_ingest_gaps(schedule: pd.DataFrame) -> pd.DataFrame:
    """Games in the schedule that are missing complete nflverse closing lines."""
    games = _schedule_games(schedule)
    if games.empty:
        return pd.DataFrame(columns=ODDS_INGEST_GAPS_COLUMNS)

    missing = games.loc[~_has_full_odds(games)].copy()
    if missing.empty:
        return pd.DataFrame(columns=ODDS_INGEST_GAPS_COLUMNS)

    id_cols = [
        col
        for col in ["game_id", "season", "week", "game_type", "gameday", "home_team", "away_team"]
        if col in missing.columns
    ]
    result = missing[id_cols].copy()
    result["gap_reason"] = missing.apply(_gap_reason, axis=1)

    available = [col for col in ODDS_INGEST_GAPS_COLUMNS if col in result.columns]
    return _dedupe(result[available], ODDS_GAPS_KEY)


def compute_odds_match_rate(schedule: pd.DataFrame, game_odds: pd.DataFrame) -> float:
    """Share of scheduled games with complete nflverse odds."""
    games = _schedule_games(schedule)
    if games.empty:
        return 0.0

    if game_odds.empty or "game_id" not in game_odds.columns:
        return 0.0

    matched_ids = set(game_odds.loc[_has_full_odds(game_odds), "game_id"].astype(str))
    scheduled_ids = set(games["game_id"].astype(str))
    if not scheduled_ids:
        return 0.0
    return len(matched_ids & scheduled_ids) / len(scheduled_ids)


def compute_season_match_rates(
    schedule: pd.DataFrame,
    game_odds: pd.DataFrame,
    *,
    seasons: list[int] | None = None,
) -> dict[int, float]:
    """Per-season odds match rates for validation."""
    games = _schedule_games(schedule)
    if games.empty:
        return {}

    if seasons is None:
        seasons = sorted(games["season"].dropna().astype(int).unique().tolist())

    rates: dict[int, float] = {}
    for season in seasons:
        season_schedule = games[games["season"] == season]
        season_odds = game_odds[game_odds["season"] == season] if not game_odds.empty else game_odds
        rates[season] = compute_odds_match_rate(season_schedule, season_odds)
    return rates


def build_odds_from_schedule(schedule: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return game odds, odds lines, latest snapshot, and ingest gaps."""
    game_odds = extract_game_odds(schedule)
    odds_lines = extract_odds_lines(game_odds)
    gaps = find_odds_ingest_gaps(schedule)
    latest = game_odds.copy()
    return game_odds, odds_lines, latest, gaps


def nflverse_odds_source_file() -> str:
    return NFLVERSE_GAMES_URL