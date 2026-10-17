"""Truncate season rows, run two backtests, and compare nfelo_blend settings."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from test_databricks_connect import _load_project_env, _profile

_load_project_env()
profile = _profile()
if not profile:
    raise SystemExit("Set DATABRICKS_CONFIG_PROFILE in .env")

season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
target = sys.argv[2] if len(sys.argv) > 2 else "prod"
blends = [0.30, 0.40]


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def summarize(blend: float) -> dict[str, float | int | None]:
    from databricks.connect import DatabricksSession

    spark = DatabricksSession.builder.profile(profile).getOrCreate()
    row = spark.sql(
        f"""
        WITH latest AS (
          SELECT g.*,
                 ROW_NUMBER() OVER (PARTITION BY g.game_id ORDER BY g.graded_at DESC) AS rn
          FROM nfl.gold.prediction_grades g
          LEFT JOIN nfl.gold.game_predictions p
            ON g.prediction_id = p.prediction_id
          WHERE g.season = {season}
            AND COALESCE(g.nfelo_blend, p.nfelo_blend) = {blend}
        )
        SELECT
          COUNT(*) AS games_graded,
          ROUND(AVG(CASE WHEN spread_push = false THEN CAST(spread_correct AS INT) END) * 100, 1)
            AS spread_accuracy_pct,
          ROUND(AVG(CASE WHEN total_push = false THEN CAST(total_correct AS INT) END) * 100, 1)
            AS total_accuracy_pct,
          ROUND(AVG(ABS(total_error)), 2) AS mae_total
        FROM latest
        WHERE rn = 1
        """
    ).collect()[0]
    return {
        "games_graded": int(row.games_graded),
        "spread_accuracy_pct": row.spread_accuracy_pct,
        "total_accuracy_pct": row.total_accuracy_pct,
        "mae_total": row.mae_total,
    }


run([sys.executable, str(REPO_ROOT / "scripts" / "ingest_nfelo_local.py"), str(season)])
run([sys.executable, str(REPO_ROOT / "scripts" / "truncate_season_predictions.py"), str(season)])

results: list[tuple[float, dict]] = []
for blend in blends:
    run([sys.executable, str(REPO_ROOT / "scripts" / "truncate_season_predictions.py"), str(season)])
    run(
        [
            "databricks",
            "bundle",
            "run",
            "nfl_backtest",
            "-t",
            target,
            "--profile",
            profile,
            "--",
            f"--season={season}",
            f"--nfelo_blend={blend}",
            "--use_nfelo=true",
        ]
    )
    results.append((blend, summarize(blend)))

print("\n=== nfelo_blend comparison ===")
for blend, metrics in results:
    print(f"\nnfelo_blend={blend}")
    for key, value in metrics.items():
        print(f"  {key}: {value}")