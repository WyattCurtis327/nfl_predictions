"""Download nflverse PBP parquet files locally (for offline staging)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nfl_predictions.nflverse_data import PbpNotAvailableError, parse_season_list
from nfl_predictions.pbp_volume import download_pbp_season_local


def main() -> None:
    parser = argparse.ArgumentParser(description="Download nflverse PBP to local output/")
    parser.add_argument(
        "--seasons",
        default="2024,2025",
        help="Comma-separated seasons (default: 2024,2025)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "output"),
        help="Local output directory",
    )
    args = parser.parse_args()

    seasons = parse_season_list(args.seasons)
    ingested_at = datetime.now(timezone.utc).isoformat()
    output_dir = Path(args.output_dir)

    for season in seasons:
        try:
            path = download_pbp_season_local(season, output_dir)
            print(f"PBP {season}: wrote {path}")
        except PbpNotAvailableError as exc:
            raise SystemExit(str(exc)) from exc

    print(f"ingested_at: {ingested_at}")


if __name__ == "__main__":
    main()