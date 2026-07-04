# nfl_predictions

NFL predictions data platform on Databricks. Ingests nflverse schedules, play-by-play, rosters, and odds into Unity Catalog `nfl`, then runs weekly Monte Carlo predictions and grading.

**Repo:** [WyattCurtis327/nfl_predictions](https://github.com/WyattCurtis327/nfl_predictions)

## Project status

Last updated: July 2026.

| Area | Status |
|------|--------|
| Phase 1 — Bootstrap | Done and validated (`nfl_bootstrap`) |
| Phase 2 — Predictions + grading | Done (`nfl_weekly_predictions`) |
| Odds API ingest | Done — DraftKings lines via `21_ingest_odds_api` |
| 2026 schedule | Loaded — 272 REG games; Week 1 = 16 games |
| Week 1 predictions | Done — `nfl.predictions.game_predictions` |
| Weekly data refresh | Done (`nfl_weekly_refresh`) |
| Full Wednesday pipeline | Done (`nfl_weekly_pipeline`) |
| `prediction_grades` | Pending — no completed week yet |
| `game_pick_metrics` view | SQL ready; deploy after first grades |
| `nfl_annual_refresh` | Not built |

### Odds sources

| Source | When | Bookmaker | Notebook |
|--------|------|-----------|----------|
| nflverse closing lines | Bootstrap / historical | `nflverse` | `20_ingest_odds_from_schedules` |
| The Odds API (live) | Weekly refresh + predictions | `draftkings` (default) | `21_ingest_odds_api` |

Live odds are staged locally (`scripts/stage_odds.py` → `staging/odds_latest.json`) because Databricks serverless cannot always reach The Odds API directly.

## Roadmap

Use this section to pick up where you left off.

### Now (pre–Week 1 kickoff)

1. **Validate the full chain** — run `nfl_weekly_pipeline` once after staging odds.
2. **Optional** — unpause the Wednesday 8 AM ET schedule on `nfl_weekly_pipeline` when you want automation.

```powershell
python scripts/stage_odds.py
python scripts/deploy_bundle.py prod
databricks bundle run nfl_weekly_pipeline -t prod --profile <your-profile>
```

### After Week 1 games complete

1. Re-run `nfl_weekly_pipeline` — `02_grade_elapsed_week` creates `prediction_grades`.
2. Pull UC descriptions for the new table:

```powershell
python scripts/pull_uc_column_descriptions.py --profile <your-profile> --include-predictions
```

3. Deploy the accuracy metric view — run `scripts/create_mv_game_pick_metrics.sql` on the SQL warehouse.
4. Re-apply descriptions if needed (`80_apply_uc_column_descriptions` with `only_schema=predictions`).

### During the 2026 season (each week)

1. `python scripts/stage_odds.py` — refresh staged lines (uses `ODDS_API_KEY` from `.env`).
2. `python scripts/deploy_bundle.py prod` — sync bundle + wheel to workspace.
3. `databricks bundle run nfl_weekly_pipeline -t prod --profile <your-profile>` — refresh data, predict next week, grade elapsed week.

**Note:** 2026 nflverse PBP is skipped until published (pre-season). `00_download_pbp` and `03_load_pbp` tolerate missing current-season files; predictions use 2025 PBP until in-season plays exist.

### Later (Feb 2027+)

- Build `nfl_annual_refresh` — annual PBP backfill, schedule merge, validation gate.
- Optional: automate `stage_odds.py` in CI or as a pre-job step; add a Databricks dashboard on `game_pick_metrics`.

## Quick start

```powershell
git clone https://github.com/WyattCurtis327/nfl_predictions.git
cd nfl_predictions
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
```

Edit `.env` with your Databricks profile and email, then sync bundle config:

```powershell
python scripts/sync_bundle_env.py
python -m build --wheel -o dist
databricks bundle validate -t prod --profile <your-profile>
python scripts/deploy_bundle.py prod
```

Run `sync_bundle_env.py` before VS Code deploy too — it removes stale `BUNDLE_VAR_failure_notifications` and sets `BUNDLE_VAR_notify_email` in `.databricks/.databricks.env`.

Configure Databricks auth once with `databricks auth login --profile <name>`. The bundle uses that profile for workspace host and credentials — nothing sensitive belongs in `databricks.yml`.

### The Odds API secret

Required for live weekly odds (not needed for bootstrap — historical odds come from nflverse):

```powershell
# Put ODDS_API_KEY in .env first, then:
python scripts/set_odds_api_secret.py

# Or interactively (PowerShell):
powershell -ExecutionPolicy Bypass -File scripts/setup_databricks_secrets.ps1
```

Secret scope defaults to `nfl`, key `odds_api_key`. In notebooks:

```python
api_key = dbutils.secrets.get(scope="nfl", key="odds_api_key")
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `DATABRICKS_CONFIG_PROFILE` | CLI profile from `~/.databrickscfg` |
| `DATABRICKS_EMAIL_ACCOUNT` | Job failure notification email |
| `ODDS_API_KEY` | The Odds API key for `scripts/stage_odds.py` |
| `BUNDLE_VAR_notify_email` | Set automatically by `sync_bundle_env.py` for VS Code deploy |

## Unity Catalog

| Schema | Tables / views |
|--------|----------------|
| `nfl.schedules` | `games` |
| `nfl.teams` | `teams` |
| `nfl.pbp` | `play_by_play` |
| `nfl.rosters` | `rosters` |
| `nfl.players` | `players`, `player_roles` |
| `nfl.odds` | `game_odds`, `odds_lines`, `game_odds_latest`, `odds_ingest_gaps` |
| `nfl.predictions` | `game_predictions`, `prediction_grades`, `game_pick_metrics` (view) |

## Jobs

| Job | Purpose | Schedule |
|-----|---------|----------|
| `nfl_bootstrap` | One-time data load | Manual |
| `nfl_weekly_refresh` | Wednesday data refresh | Paused Wed 8 AM ET |
| `nfl_weekly_predictions` | Odds → predict → grade → UC descriptions | Manual |
| `nfl_weekly_pipeline` | `nfl_weekly_refresh` then `nfl_weekly_predictions` | Paused Wed 8 AM ET |
| `nfl_annual_refresh` | Annual backfill (planned) | — |

### `nfl_bootstrap` task order

1. **Parallel:** `00_download_pbp`, `01_ingest_teams`, `02_ingest_schedules`, `03_ingest_rosters`
2. **After schedules:** `04_ingest_odds` (nflverse closing lines from `games.csv`)
3. **After download + schedules:** `05_load_pbp`
4. **Serial:** `06_build_players` → `07_apply_uc_column_descriptions` → `08_validate_bootstrap`

```powershell
databricks bundle run nfl_bootstrap -t prod --profile <your-profile>
```

### `nfl_weekly_refresh` task order

1. **Parallel:** `00_download_pbp`, `01_ingest_schedules`, `02_ingest_rosters`
2. **Parallel:** `03_load_pbp`, `04_ingest_odds_api`
3. **Serial:** `05_build_players` → `06_apply_refresh_column_descriptions` → `07_validate_weekly_refresh`

```powershell
python scripts/stage_odds.py
python scripts/deploy_bundle.py prod
databricks bundle run nfl_weekly_refresh -t prod --profile <your-profile>
```

### `nfl_weekly_predictions` task order

1. `00_ingest_odds_api`
2. `01_predict_upcoming_week`
3. `02_grade_elapsed_week` (skips when no completed week)
4. `03_apply_predictions_column_descriptions`

```powershell
databricks bundle run nfl_weekly_predictions -t prod --profile <your-profile>
```

### `nfl_weekly_pipeline` (recommended weekly run)

```powershell
python scripts/stage_odds.py
python scripts/deploy_bundle.py prod
databricks bundle run nfl_weekly_pipeline -t prod --profile <your-profile>
```

## Notebook naming

Notebooks and job tasks use `00`–`99` prefixes. File prefixes reflect the shared data-flow sequence; task keys use each job's local run order (e.g. bootstrap `04_ingest_odds`, weekly refresh `04_ingest_odds_api`).

| Prefix | Notebook |
|--------|----------|
| 00 | `00_download_pbp_to_volume` |
| 10–12 | teams, schedules, rosters ingest |
| 20–21 | nflverse odds, Odds API ingest |
| 30 | `30_load_pbp_from_volume` |
| 40 | `40_build_players` |
| 50–60 | predict, grade |
| 80 | `80_apply_uc_column_descriptions` |
| 90–91 | bootstrap / weekly validation |

## Schema metadata

Unity Catalog column comments live in `resources/schema/`.

**Pull** workspace comments into the repo after editing in Databricks:

```powershell
python scripts/pull_uc_column_descriptions.py --profile <your-profile>
python scripts/pull_uc_column_descriptions.py --profile <your-profile> --include-predictions
```

`pull_uc_column_descriptions.py` continues when `prediction_grades` does not exist yet.

**Apply** after data loads: `80_apply_uc_column_descriptions` reads `resources/schema/` and runs `COMMENT ON TABLE` / `ALTER COLUMN ... COMMENT`.

## Conventions

- Playoff game types: `REG`, `WC`, `DIV`, `CON`, `SB` (preseason never loaded)
- Player key: `gsis_id` → `player_id`
- Game key: nflverse `game_id`
- All tables include `ingested_at` and `_source_file`
- Preferred live bookmaker: `draftkings` (bundle var `preferred_bookmaker`)

## Resuming work

When you return to this project:

1. Read **Project status** and **Roadmap** above.
2. Open `resources/*.yml` for current job DAGs.
3. Ask the agent: *"What's next for nfl_predictions?"* — it will read repo state and continue from the roadmap.