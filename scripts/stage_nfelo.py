"""Fetch nfelo power ratings and stage them for Databricks ingest."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nfl_predictions.nfelo import NFELO_SOURCE, fetch_nfelo_snapshot

STAGING = ROOT / "staging" / "nfelo_ratings.json"


def main() -> None:
    ingested_at = datetime.now(timezone.utc)
    ratings = fetch_nfelo_snapshot()
    STAGING.parent.mkdir(exist_ok=True)
    payload = {
        "ingested_at": ingested_at.isoformat(),
        "source": NFELO_SOURCE,
        "ratings": ratings.to_dict(orient="records"),
    }
    with STAGING.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    print(f"Fetched {len(ratings)} nfelo team ratings")
    print(f"Staged ratings for Databricks ingest: {STAGING}")


if __name__ == "__main__":
    main()