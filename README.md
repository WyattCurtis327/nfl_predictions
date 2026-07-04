# nfl_predictions

NFL predictions data platform on Databricks. Ingests nflverse schedules, play-by-play, rosters, and odds into Unity Catalog `nfl`, then runs weekly Monte Carlo predictions and grading.

## Quick start

```powershell
git clone <your-repo-url>
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

Optional: store The Odds API key for **live weekly odds** (not needed for bootstrap — historical odds come from nflverse):

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
| `BUNDLE_VAR_notify_email` | Set automatically by `sync_bundle_env.py` for VS Code deploy |

## Unity Catalog

| Schema | Tables |
|--------|--------|
| `nfl.schedules` | `games` |
| `nfl.teams` | `teams` |
| `nfl.pbp` | `play_by_play` |
| `nfl.rosters` | `rosters` |
| `nfl.players` | `players`, `player_roles` |
| `nfl.odds` | `game_odds`, `odds_lines`, `game_odds_latest`, … |
| `nfl.predictions` | `game_predictions`, `prediction_grades`, `game_pick_metrics` |

## Jobs

- `nfl_bootstrap` — one-time data load (teams → schedules → nflverse odds → PBP → rosters → players → validate)
- `nfl_weekly_refresh` — Wednesday data refresh (PBP → schedules → rosters → odds API → players → validate)
- `nfl_weekly_predictions` — live odds ingest → predict → grade → UC descriptions
- `nfl_weekly_pipeline` — runs `nfl_weekly_refresh`, then `nfl_weekly_predictions` (paused Wed 8 AM ET schedule)
- `nfl_annual_refresh` — Feb 15 refresh (planned)

### Notebook naming

Notebooks and job tasks use `00`–`99` prefixes for pipeline order. File prefixes reflect the shared data-flow sequence; task keys use each job's local run order (e.g. bootstrap `04_ingest_odds`, weekly refresh `04_ingest_odds_api`).

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

### Weekly refresh waves

1. **Parallel:** `00_download_pbp`, `01_ingest_schedules`, `02_ingest_rosters`
2. **Parallel:** `03_load_pbp`, `04_ingest_odds_api`
3. **Serial:** `05_build_players` → `06_apply_refresh_column_descriptions` → `07_validate_weekly_refresh`

Before running odds ingest on Databricks, stage lines locally:

```powershell
python scripts/stage_odds.py
python scripts/deploy_bundle.py prod
databricks bundle run nfl_weekly_refresh -t prod --profile <your-profile>
```

For the full Wednesday sequence (refresh + predictions):

```powershell
databricks bundle run nfl_weekly_pipeline -t prod --profile <your-profile>
```

### Bootstrap waves

1. **Parallel:** `00_download_pbp`, `01_ingest_teams`, `02_ingest_schedules`, `03_ingest_rosters`
2. **After schedules:** `04_ingest_odds` (nflverse closing lines from `games.csv`)
3. **After download + schedules:** `05_load_pbp`
4. **Serial:** `06_build_players` → `07_apply_uc_column_descriptions` → `08_validate_bootstrap`

## Schema metadata

Unity Catalog column comments for bootstrap tables live in `resources/schema/`.

- **Pull** workspace comments into the repo after editing in Databricks:

```powershell
python scripts/pull_uc_column_descriptions.py --profile <your-profile>
```

- **Apply** on every bootstrap run: `80_apply_uc_column_descriptions` reads `resources/schema/` and runs `COMMENT ON TABLE` / `ALTER COLUMN ... COMMENT` after data loads.

## Conventions

- Playoff game types: `REG`, `WC`, `DIV`, `CON`, `SB` (preseason never loaded)
- Player key: `gsis_id` → `player_id`
- Game key: nflverse `game_id`
- All tables include `ingested_at` and `_source_file`