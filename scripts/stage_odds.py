"""Fetch Odds API lines locally and stage them for Databricks ingest."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nfl_predictions.odds_api import OddsApiError, fetch_nfl_odds

STAGING = ROOT / "staging" / "odds_latest.json"


def main() -> None:
    ingested_at = datetime.now(timezone.utc)
    try:
        odds_games, headers = fetch_nfl_odds()
    except OddsApiError as exc:
        raise SystemExit(str(exc)) from exc

    STAGING.parent.mkdir(exist_ok=True)
    payload = {
        "ingested_at": ingested_at.isoformat(),
        "headers": headers,
        "games": odds_games,
    }
    with STAGING.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    print(f"Fetched {len(odds_games)} games")
    print(f"Requests remaining: {headers.get('x-requests-remaining')}")
    print(f"Staged odds for Databricks ingest: {STAGING}")


if __name__ == "__main__":
    main()