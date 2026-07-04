"""Query nfl.odds.odds_ingest_gaps for unmapped team rows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from test_databricks_connect import _load_project_env  # noqa: E402
from databricks.connect import DatabricksSession  # noqa: E402


def main() -> None:
    _load_project_env()
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE", "wyatts_databricks")
    spark = DatabricksSession.builder.profile(profile).getOrCreate()
    print("=== odds_ingest_gaps by gap_reason ===")
    spark.sql(
        """
        SELECT gap_reason, COUNT(*) AS n
        FROM nfl.odds.odds_ingest_gaps
        GROUP BY gap_reason
        ORDER BY n DESC
        """
    ).show(truncate=False)

    print("=== unmapped_team_name sample ===")
    spark.sql(
        """
        SELECT game_id, season, week, gameday, away_team, home_team, gap_reason
        FROM nfl.odds.odds_ingest_gaps
        WHERE gap_reason = 'unmapped_team_name'
        LIMIT 20
        """
    ).show(truncate=False)


if __name__ == "__main__":
    main()