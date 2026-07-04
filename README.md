# nfl_predictions

NFL predictions data platform on Databricks. Ingests nflverse schedules, play-by-play, rosters, odds, and nfelo power ratings into Unity Catalog `nfl`, then runs weekly Monte Carlo predictions and grading.

**Repo:** [WyattCurtis327/nfl_predictions](https://github.com/WyattCurtis327/nfl_predictions)

## Project status

Last updated: July 2026.

| Area | Status |
|------|--------|
| Phase 1 — Bootstrap | Done (`nfl_bootstrap`) |
| Phase 2 — Predictions + grading | Done (`nfl_weekly_predictions`) |
| nfelo integration | Done — team ratings + per-game lines blended into simulations |
| Odds API ingest | Done — DraftKings lines via `21_ingest_odds_api` |
| 2026 schedule | Loaded — 272 REG games |
| Weekly data refresh | Done (`nfl_weekly_refresh`, includes nfelo ingest) |
| Full Wednesday pipeline | Done (`nfl_weekly_pipeline`) |
| Season backtest | Done (`nfl_backtest`) — replay prior-year PBP, grade outcomes |
| `prediction_grades` | Live — populated after completed weeks / backtests |
| `game_pick_metrics` | Metric view deployed; powers Genie space |
| Genie space | `NFL Pick Metrics` — natural-language Q&A on pick accuracy |
| CI | GitHub Actions — pytest, wheel build, bundle validate |

### Prediction model (high level)

For each upcoming game:

1. **PBP baseline** — team scoring profiles from prior + current-season play-by-play.
2. **nfelo blend** (`nfelo_blend`, default 0.30) — pulls expected margin toward nfelo team ratings or per-game lines when available.
3. **Market blend** (`market_blend`, default 0.35) — calibrates to DraftKings spread/total.
4. **Monte Carlo** — 10k simulations → spread/total picks above `pick_threshold`.

nfelo data is refreshed weekly via `22_ingest_nfelo_ratings` into `nfl.teams.nfelo_ratings` and `nfl.teams.nfelo_games`. For future seasons before nfelo publishes game lines, team-rating fallback uses the prior season's final snapshot.

### Odds sources

| Source | When | Bookmaker | Notebook |
|--------|------|-----------|----------|
| nflverse closing lines | Bootstrap / historical | `nflverse` | `20_ingest_odds_from_schedules` |
| The Odds API (live) | Weekly refresh | `draftkings` (default) | `21_ingest_odds_api` |

Live odds are staged locally (`scripts/stage_odds.py` → `staging/odds_latest.json`) because Databricks serverless cannot always reach The Odds API directly.

## Quick start

```powershell
git clone https://github.com/WyattCurtis327/nfl_predictions.git
cd nfl_predictions
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

Edit `.env` with your Databricks profile, notification email, warehouse ID, and (optionally) Odds API key. **Never commit `.env`.**

```powershell
python scripts/sync_bundle_env.py
python -m build --wheel -o dist
databricks bundle validate -t prod --profile <your-profile>
python scripts/deploy_bundle.py prod
```

`sync_bundle_env.py` writes your CLI profile host into `databricks.yml`, syncs serverless Connect settings, and pushes `notify_email` / `sql_warehouse_id` into bundle variable overrides.

Configure Databricks auth once with `databricks auth login --profile <name>`. API keys and tokens belong in `.env` or Databricks secret scopes — not in source files.

### Weekly operator run

```powershell
powershell -ExecutionPolicy Bypass -File scripts/weekly_run.ps1 -Profile <your-profile>
```

Stages odds, builds the wheel, deploys the bundle + metric view + Genie space, and runs `nfl_weekly_pipeline`.

**Note:** 2026 nflverse PBP is skipped until published. `00_download_pbp` and `03_load_pbp` tolerate missing current-season files; predictions use 2025 PBP until in-season plays exist.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `DATABRICKS_CONFIG_PROFILE` | CLI profile from `~/.databrickscfg` |
| `DATABRICKS_EMAIL_ACCOUNT` | Job failure notification email |
| `DATABRICKS_WAREHOUSE_ID` | SQL warehouse for Genie + metric-view deploy scripts |
| `ODDS_API_KEY` | The Odds API key for `scripts/stage_odds.py` (optional for bootstrap) |
| `BUNDLE_VAR_notify_email` | Set automatically by `sync_bundle_env.py` |
| `DATABRICKS_CLUSTER_ID` | **Do not set** — conflicts with VS Code serverless Connect |

### The Odds API secret (production ingest)

For live weekly odds in Databricks notebooks, store the key in a secret scope (not in repo):

```powershell
# Put ODDS_API_KEY in .env first, then:
python scripts/set_odds_api_secret.py --profile <your-profile>

# Or interactively:
powershell -ExecutionPolicy Bypass -File scripts/setup_databricks_secrets.ps1
```

Default scope/key: `nfl` / `odds_api_key`. Notebooks read via `dbutils.secrets.get(scope="nfl", key="odds_api_key")`.

### Databricks Connect (VS Code)

```powershell
python scripts/test_databricks_connect.py
```

`.vscode/settings.json` loads `.env` and a folder-open task runs `sync_bundle_env.py`. Reload the window once after cloning.

## Unity Catalog

| Schema | Tables / views |
|--------|----------------|
| `nfl.schedules` | `games` |
| `nfl.teams` | `teams`, `nfelo_ratings`, `nfelo_games` |
| `nfl.pbp` | `play_by_play` |
| `nfl.rosters` | `rosters` |
| `nfl.players` | `players`, `player_roles` |
| `nfl.odds` | `game_odds`, `odds_lines`, `game_odds_latest`, `odds_ingest_gaps` |
| `nfl.predictions` | `game_predictions`, `prediction_grades`, `game_pick_metrics` (metric view) |

## Jobs

| Job | Purpose | Schedule |
|-----|---------|----------|
| `nfl_bootstrap` | One-time data load | Manual |
| `nfl_weekly_refresh` | Wednesday data refresh (incl. nfelo) | Paused Wed 8 AM ET |
| `nfl_weekly_predictions` | Predict + grade | Manual |
| `nfl_weekly_pipeline` | Refresh then predictions | Paused Wed 8 AM ET |
| `nfl_backtest` | Replay a season with prior-year PBP | Manual |
| `nfl_annual_refresh` | Annual PBP backfill + validation | Manual (February) |

Bundle variables for simulation tuning: `n_simulations`, `market_blend`, `nfelo_blend`, `pick_threshold` in `databricks.yml`.

### Backtest a completed season

```powershell
databricks bundle run nfl_backtest -t prod --profile <your-profile> -- `
  --season=2025 --nfelo_blend=0.30 --use_nfelo=true
```

Writes to `game_predictions` and `prediction_grades`. Use `scripts/truncate_season_predictions.py` to clear a season before re-running.

### Genie space

The `nfl_game_pick_metrics` Genie space is defined in:

- `resources/nfl_game_pick_metrics.genie_space.yml`
- `src/nfl_game_pick_metrics.geniespace.json`

Deployed with the bundle (requires `DATABRICKS_WAREHOUSE_ID` in `.env`). Open after deploy:

```powershell
databricks bundle open nfl_game_pick_metrics -t prod --profile <your-profile>
```

To pull UI edits back into git: `databricks bundle generate genie-space --resource nfl_game_pick_metrics --force`

### `nfl_weekly_refresh` task order

1. **Parallel:** `00_download_pbp`, `01_ingest_schedules`, `02_ingest_rosters`
2. **Parallel:** `03_load_pbp`, `04_ingest_nfelo_ratings`, `05_ingest_odds_api`
3. **Serial:** `06_build_players` → `07_apply_refresh_column_descriptions` → `08_validate_weekly_refresh`

### `nfl_weekly_predictions` task order

1. `00_predict_upcoming_week`
2. `01_grade_elapsed_week` (skips when no completed week)
3. `02_apply_predictions_column_descriptions`

`deploy_bundle.py` deploys the `game_pick_metrics` metric view automatically (skip with `--skip-metric-view`).

## Notebook naming

| Prefix | Notebook |
|--------|----------|
| 00 | `00_download_pbp_to_volume` |
| 10–12 | teams, schedules, rosters ingest |
| 20–22 | nflverse odds, Odds API, nfelo ingest |
| 30 | `30_load_pbp_from_volume` |
| 40 | `40_build_players` |
| 50–55 | predict, backtest |
| 60 | `60_grade_elapsed_week` |
| 80 | `80_apply_uc_column_descriptions` |
| 90–91 | bootstrap / weekly validation |

## Ops scripts (local / one-off)

| Script | Purpose |
|--------|---------|
| `weekly_run.ps1` | Stage odds, deploy, run pipeline |
| `stage_odds.py` | Fetch live odds to `staging/odds_latest.json` |
| `ingest_nfelo_local.py` | One-off nfelo ingest via Connect |
| `truncate_season_predictions.py` | Delete season rows from predictions/grades |
| `compare_nfelo_blend.py` | Backtest two `nfelo_blend` values and compare |
| `pull_uc_column_descriptions.py` | Pull UC comments into `resources/schema/` |
| `test_databricks_connect.py` | Smoke-test Connect session |

## Schema metadata

Unity Catalog column comments live in `resources/schema/`. Apply via `80_apply_uc_column_descriptions`; pull edits back with `pull_uc_column_descriptions.py`.

## Conventions

- Playoff game types: `REG`, `WC`, `DIV`, `CON`, `SB`
- Player key: `gsis_id` → `player_id`
- Game key: nflverse `game_id`
- All tables include `ingested_at` and `_source_file`
- Preferred live bookmaker: `draftkings` (bundle var `preferred_bookmaker`)
- Bundle uses **direct deployment engine** (`bundle.engine: direct` in `databricks.yml`)

## Resuming work

1. Read **Project status** above.
2. Open `resources/*.yml` for current job DAGs.
3. Run `python scripts/sync_bundle_env.py` after any `.env` change.