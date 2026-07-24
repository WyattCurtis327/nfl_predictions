# nfl_predictions

NFL predictions data platform on Databricks. Ingests nflverse schedules, play-by-play, rosters, odds, and nfelo power ratings into Unity Catalog `nfl`, then runs weekly Monte Carlo predictions and grading.

**Repo:** [WyattCurtis327/nfl_predictions](https://github.com/WyattCurtis327/nfl_predictions)

## What you need

| Requirement | Notes |
|-------------|--------|
| Python 3.10+ (3.12 recommended) | Local venv for scripts, tests, wheel build |
| [Databricks CLI](https://docs.databricks.com/dev-tools/cli/index.html) | Auth via `databricks auth login` |
| Databricks workspace with Unity Catalog | Jobs, volumes, apps, Genie |
| SQL warehouse | Genie spaces, metric views, Streamlit apps |
| Optional: [The Odds API](https://the-odds-api.com) key | Live weekly lines only; nflverse bootstrap works without it |

This repository is meant to be **cloned and configured for your own workspace**. It does not ship credentials. See [SECURITY.md](SECURITY.md).

## Quick start

```powershell
git clone https://github.com/WyattCurtis327/nfl_predictions.git
cd nfl_predictions
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

```bash
git clone https://github.com/WyattCurtis327/nfl_predictions.git
cd nfl_predictions
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

1. Edit **`.env`** with your Databricks CLI profile, notification email, warehouse ID, and (optionally) Odds API key.
2. Authenticate once: `databricks auth login --profile <your-profile>`
3. Sync gitignored local env (host, serverless Connect, bundle var overrides):

```powershell
python scripts/sync_bundle_env.py
python -m build --wheel -o dist
databricks bundle validate -t prod --profile <your-profile>
python scripts/deploy_bundle.py prod
```

**Never commit `.env`.**  
`sync_bundle_env.py` writes your workspace host and profile into **gitignored** `.env` / `.databricks/` only. Committed `databricks.yml` keeps a public host placeholder so clones do not inherit someone else’s workspace.

Optional: install a pre-commit hook that runs the public-ready check:

```bash
git config core.hooksPath .githooks
```

### Weekly operator run

```powershell
powershell -ExecutionPolicy Bypass -File scripts/weekly_run.ps1 -Profile <your-profile>
```

Stages odds, builds the wheel, deploys the bundle + metric view + Genie space, and runs `nfl_weekly_pipeline`.

**Note:** 2026 nflverse PBP is skipped until published. `00_download_pbp` and `03_load_pbp` tolerate missing current-season files; predictions use 2025 PBP until in-season plays exist.

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABRICKS_CONFIG_PROFILE` | Yes | CLI profile from `~/.databrickscfg` |
| `DATABRICKS_EMAIL_ACCOUNT` | Yes (deploy) | Job failure notification email |
| `DATABRICKS_WAREHOUSE_ID` | Yes (Genie/apps) | SQL warehouse for Genie + metric-view + apps |
| `ODDS_API_KEY` | No | The Odds API key for `scripts/stage_odds.py` |
| `DATABRICKS_HOST` | Auto | Filled by `sync_bundle_env.py` from your profile |
| `BUNDLE_VAR_notify_email` | Auto | Set by `sync_bundle_env.py` |
| `DATABRICKS_CLUSTER_ID` | **Do not set** | Conflicts with VS Code serverless Connect |

Template: [`.env.example`](.env.example). Secrets and identity never belong in `databricks.yml` or notebooks.

### The Odds API secret (production ingest)

For live weekly odds in Databricks notebooks, store the key in a secret scope (not in the repo):

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

### Public-ready check

```powershell
python scripts/check_public_ready.py
```

Fails if git-tracked files contain real workspace hosts, personal absolute paths, live odds dumps, or secret-like literals. CI runs this on every push/PR.

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
| Weekly picks app | `nfl-weekly-picks` — read-only Streamlit pick board |
| CI | GitHub Actions — public-ready check, pytest, wheel build, bundle validate |

### Prediction model (high level)

For each upcoming game:

1. **PBP baseline** — team scoring profiles from prior + current-season play-by-play.
2. **nfelo blend** (`nfelo_blend`, default 0.30) — pulls expected margin toward nfelo team ratings or per-game lines when available.
3. **Market blend** (`market_blend`, default 0.35) — calibrates to DraftKings spread/total.
4. **Monte Carlo** — 10k simulations → spread/total picks above `pick_threshold`.

nfelo data is refreshed weekly via `22_ingest_nfelo_ratings` into `nfl.landing.nfelo_ratings` and `nfl.landing.nfelo_games`. For future seasons before nfelo publishes game lines, team-rating fallback uses the prior season's final snapshot.

### Odds sources

| Source | When | Bookmaker | Notebook |
|--------|------|-----------|----------|
| nflverse closing lines | Bootstrap / historical | `nflverse` | `20_ingest_odds_from_schedules` |
| The Odds API (live) | Weekly refresh | `draftkings` (default) | `21_ingest_odds_api` |

Live odds are staged locally (`scripts/stage_odds.py` → `staging/odds_latest.json`, gitignored). Shape reference: `staging/odds_latest.example.json`. Databricks serverless cannot always reach The Odds API directly.

## Unity Catalog (medallion)

Default catalog name is `nfl` (override with bundle variable `catalog`).

| Schema | Role | Tables / views |
|--------|------|----------------|
| `nfl.landing` | Raw ingest | `games`, `teams`, `nfelo_*`, `play_by_play`, `rosters`, `players`, `player_roles`, `game_odds`, `odds_lines`, `game_odds_latest`, `odds_ingest_gaps` |
| `nfl.bronze` / `nfl.silver` | Curated layers | Materialized views from the medallion pipeline |
| `nfl.gold` | Product / analytics | `game_predictions`, `current_predictions`, `prediction_grades`, `prediction_rca`, `pick_miss_rca`, `game_pick_metrics`, gold aggregates |

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

- `resources/genie/nfl_game_pick_metrics.genie_space.yml` (and related resources)
- `src/nfl_game_pick_metrics.geniespace.json`

Deployed with the bundle (requires `DATABRICKS_WAREHOUSE_ID` in `.env`). Open after deploy:

```powershell
databricks bundle open nfl_game_pick_metrics -t prod --profile <your-profile>
```

To pull UI edits back into git: `databricks bundle generate genie-space --resource nfl_game_pick_metrics --force`

### Weekly picks app (Phase 1)

Read-only Streamlit dashboard for the latest spread/total picks per game.

- Code: `app/weekly_picks/`
- Bundle resource: `resources/nfl_weekly_picks.app.yml`
- Requires `DATABRICKS_WAREHOUSE_ID` in `.env` (same warehouse as Genie)

```powershell
python scripts/sync_bundle_env.py
databricks bundle deploy -t prod --profile <your-profile>
databricks bundle run nfl_weekly_picks -t prod --profile <your-profile>
```

Open from bundle summary or the Apps page in the workspace.

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
| `stage_odds.py` | Fetch live odds to `staging/odds_latest.json` (gitignored) |
| `sync_bundle_env.py` | Sync `.env` → gitignored Databricks/VS Code env |
| `check_public_ready.py` | Guard against secrets/identity in git |
| `ingest_nfelo_local.py` | One-off nfelo ingest via Connect |
| `truncate_season_predictions.py` | Delete season rows from predictions/grades |
| `compare_nfelo_blend.py` | Backtest two `nfelo_blend` values and compare |
| `pull_uc_column_descriptions.py` | Pull UC comments into `resources/schema/` |
| `test_databricks_connect.py` | Smoke-test Connect session |

## Schema metadata

Unity Catalog column comments live under `resources/schema/nfl/landing/` and `resources/schema/nfl/gold/`. Apply via `80_apply_uc_column_descriptions`; pull edits back with `pull_uc_column_descriptions.py`.

## Conventions

- Playoff game types: `REG`, `WC`, `DIV`, `CON`, `SB`
- Player key: `gsis_id` → `player_id`
- Game key: nflverse `game_id`
- All tables include `ingested_at` and `_source_file`
- Preferred live bookmaker: `draftkings` (bundle var `preferred_bookmaker`)
- Bundle uses **direct deployment engine** (`bundle.engine: direct` in `databricks.yml`)
- Deploy paths are per-user: `/Workspace/Users/${workspace.current_user.userName}/.bundle/...`

## Security & multi-tenant notes

- **Your** catalog, warehouse, secret scope, and Genie spaces are created in **your** workspace when you deploy.
- Do not commit `databricks.yml` host/profile changes; keep the public placeholder and use `.env`.
- Live odds and local dumps under `staging/` are gitignored except `odds_latest.example.json`.
- Details: [SECURITY.md](SECURITY.md).

## Resuming work

1. Read **Project status** above.
2. Open `resources/*.yml` for current job DAGs.
3. Run `python scripts/sync_bundle_env.py` after any `.env` change.
4. Run `python scripts/check_public_ready.py` before pushing.
