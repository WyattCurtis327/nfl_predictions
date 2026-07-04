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

### Weekly refresh waves

1. **Parallel:** `download_pbp` (current season), `ingest_schedules`, `ingest_rosters`
2. **Parallel:** `load_pbp`, `ingest_odds_api` (needs schedules)
3. **Serial:** `build_players` → `apply_refresh_column_descriptions` → `validate_weekly_refresh`

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

1. **Parallel:** `download_pbp`, `ingest_teams`, `ingest_schedules`
2. **After schedules:** `ingest_odds` (nflverse closing lines from `games.csv`)
3. **Parallel:** `load_pbp` (needs schedules), `ingest_rosters`
4. **Serial:** `build_players` → `apply_uc_column_descriptions` → `validate_bootstrap`

## Schema metadata

Unity Catalog column comments for bootstrap tables live in `resources/schema/`.

- **Pull** workspace comments into the repo after editing in Databricks:

```powershell
python scripts/pull_uc_column_descriptions.py --profile <your-profile>
```

- **Apply** on every bootstrap run: `apply_uc_column_descriptions` reads `resources/schema/` and runs `COMMENT ON TABLE` / `ALTER COLUMN ... COMMENT` after data loads.

## Conventions

- Playoff game types: `REG`, `WC`, `DIV`, `CON`, `SB` (preseason never loaded)
- Player key: `gsis_id` → `player_id`
- Game key: nflverse `game_id`
- All tables include `ingested_at` and `_source_file`