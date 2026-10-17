"""Audit Odds API team names against the nfl_predictions mapping table."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from nfl_predictions.nflverse_data import fetch_teams  # noqa: E402
from nfl_predictions.odds_api import find_unmapped_team_gaps, match_game_ids  # noqa: E402
from nfl_predictions.teams import TEAM_NAME_TO_ABBR, to_abbr, unmapped_team_names  # noqa: E402

STAGING = REPO_ROOT / "staging" / "odds_latest.json"


def _load_staged_games() -> list[dict]:
    if not STAGING.exists():
        raise SystemExit(f"Missing staged odds: {STAGING}")
    payload = json.loads(STAGING.read_text(encoding="utf-8"))
    return payload.get("games", [])


def _nflverse_team_names() -> pd.DataFrame:
    teams = fetch_teams()
    cols = [c for c in ("team_abbr", "team_name", "team_nick", "team_id") if c in teams.columns]
    return teams[cols].drop_duplicates()


def main() -> int:
    games = _load_staged_games()
    all_names = sorted({g["away_team"] for g in games} | {g["home_team"] for g in games})
    unmapped = unmapped_team_names(all_names)

    print("=== Staged Odds API team audit ===")
    print(f"Games: {len(games)}")
    print(f"Unique team names: {len(all_names)}")
    print(f"Mapped: {len(all_names) - len(unmapped)}")
    print(f"Unmapped: {len(unmapped)}")
    if unmapped:
        for name in unmapped:
            print(f"  - {name}")
    else:
        print("  (none)")

    print("\n=== Full name -> abbr map (staged data) ===")
    for name in all_names:
        print(f"  {name!r} -> {to_abbr(name)}")

    gaps = find_unmapped_team_gaps(games)
    print(f"\nUnmapped gap rows: {len(gaps)}")

    legacy = [
        "Oakland Raiders",
        "Washington Football Team",
        "Washington Redskins",
        "St. Louis Rams",
        "San Diego Chargers",
    ]
    print("\n=== Legacy Odds API aliases (not in current staged file) ===")
    for name in legacy:
        print(f"  {name!r} -> {to_abbr(name)}")

    print("\n=== nflverse teams.csv reference ===")
    nfl_teams = _nflverse_team_names()
    print(nfl_teams.to_string(index=False))

    mapped_abbrs = set(TEAM_NAME_TO_ABBR.values())
    nfl_abbrs = set(nfl_teams["team_abbr"].astype(str)) if "team_abbr" in nfl_teams.columns else set()
    missing_from_map = sorted(nfl_abbrs - mapped_abbrs)
    extra_in_map = sorted(mapped_abbrs - nfl_abbrs)
    print(f"\nAbbr in nflverse but not in Odds map: {missing_from_map or '(none)'}")
    print(f"Abbr in Odds map but not in nflverse: {extra_in_map or '(none)'}")

    # Schedule join simulation using nflverse schedule if available
    try:
        from nfl_predictions.nflverse_data import fetch_season_schedule

        schedule = fetch_season_schedule(2026)
        lookup = match_game_ids(games, schedule)
        no_match = [meta for meta in lookup.values() if not meta.get("game_id")]
        unmapped_match = [
            meta
            for meta in no_match
            if meta.get("away_abbr") and meta.get("home_abbr")
        ]
        print("\n=== Schedule join (2026) ===")
        print(f"API games: {len(games)}")
        print(f"No game_id match: {len(no_match)}")
        print(f"  (abbr mapped but schedule miss): {len(unmapped_match)}")
        if unmapped_match[:5]:
            for meta in unmapped_match[:5]:
                print(
                    f"  {meta.get('away_abbr')} @ {meta.get('home_abbr')} "
                    f"on {meta.get('gameday')}"
                )
    except Exception as exc:
        print(f"\nSchedule join skipped: {exc}")

    return 1 if unmapped else 0


if __name__ == "__main__":
    raise SystemExit(main())