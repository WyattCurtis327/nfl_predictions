"""Ingest nfelo ratings into UC via Databricks Connect (one-off helper)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from test_databricks_connect import _load_project_env, _profile

_load_project_env()
profile = _profile()
if not profile:
    raise SystemExit("Set DATABRICKS_CONFIG_PROFILE in .env")

from databricks.connect import DatabricksSession

from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.nfelo import NFELO_SOURCE, fetch_nfelo_games, fetch_nfelo_snapshot
from nfl_predictions.spark_io import write_delta_table
from nfl_predictions.uc_paths import UcPaths

schedule_season = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
fetch_games = sys.argv[2].lower() != "false" if len(sys.argv) > 2 else True

spark = DatabricksSession.builder.profile(profile).getOrCreate()
paths = UcPaths()
ratings_table = paths.nfelo_ratings_table()
games_table = paths.nfelo_games_table()

ratings_pdf = stamp_dataframe(fetch_nfelo_snapshot(), source_file=NFELO_SOURCE)
write_delta_table(spark, ratings_pdf, ratings_table, dedupe_keys=["season", "week", "team"])
print(f"Wrote {len(ratings_pdf)} rows to {ratings_table}")

if fetch_games:
    games_pdf = fetch_nfelo_games()
    games_pdf["season"] = (
        games_pdf["game_id"].astype(str).str.extract(r"^(\d{4})_")[0].astype("Int64")
    )
    games_pdf = games_pdf[games_pdf["season"] == schedule_season].copy()
    if games_pdf.empty:
        print(f"No nfelo_games rows for season {schedule_season}; skipped {games_table}")
    else:
        games_pdf = stamp_dataframe(games_pdf, source_file=NFELO_SOURCE)
        write_delta_table(spark, games_pdf, games_table, dedupe_keys=["game_id"])
        print(f"Wrote {len(games_pdf)} rows to {games_table}")