# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Landing Migration - Final Step (historical)
# MAGIC %md
# MAGIC # Complete Landing Migration — historical notebook
# MAGIC
# MAGIC **Superseded by the full path cutover in git.** Jobs, apps, and `uc_paths`
# MAGIC now target `nfl.landing` (domain) and `nfl.gold` (predictions) directly.
# MAGIC Keep this notebook only as a record of the intermediate view-based migration.
# MAGIC
# MAGIC ## Status (at time of migration)
# MAGIC - 16 tables copied to `nfl.landing`
# MAGIC - Pipeline updated to read from landing
# MAGIC - Legacy schemas later removed; product code cut over to landing/gold
# MAGIC
# MAGIC ## Original view-cutover cells (do not re-run on a cut-over workspace)

# COMMAND ----------

# DBTITLE 1,Category A - Schedules Schema
# MAGIC %sql
# MAGIC -- Replace schedules.games table with view
# MAGIC DROP TABLE IF EXISTS nfl.schedules.games;
# MAGIC CREATE VIEW nfl.schedules.games AS SELECT * FROM nfl.landing.games;
# MAGIC
# MAGIC -- Verify
# MAGIC SELECT 'schedules.games' as table_name, COUNT(*) as row_count FROM nfl.schedules.games;

# COMMAND ----------

# DBTITLE 1,Category A - Teams Schema
# MAGIC %sql
# MAGIC -- Replace teams.teams table with view
# MAGIC DROP TABLE IF EXISTS nfl.teams.teams;
# MAGIC CREATE VIEW nfl.teams.teams AS SELECT * FROM nfl.landing.teams;
# MAGIC
# MAGIC -- Replace teams.nfelo tables with views
# MAGIC DROP TABLE IF EXISTS nfl.teams.nfelo_games;
# MAGIC CREATE VIEW nfl.teams.nfelo_games AS SELECT * FROM nfl.landing.nfelo_games;
# MAGIC
# MAGIC DROP TABLE IF EXISTS nfl.teams.nfelo_ratings;
# MAGIC CREATE VIEW nfl.teams.nfelo_ratings AS SELECT * FROM nfl.landing.nfelo_ratings;
# MAGIC
# MAGIC -- Verify
# MAGIC SELECT 'teams.teams' as table_name, COUNT(*) FROM nfl.teams.teams
# MAGIC UNION ALL SELECT 'teams.nfelo_games', COUNT(*) FROM nfl.teams.nfelo_games
# MAGIC UNION ALL SELECT 'teams.nfelo_ratings', COUNT(*) FROM nfl.teams.nfelo_ratings;

# COMMAND ----------

# DBTITLE 1,Category A - Players & Rosters Schema
# MAGIC %sql
# MAGIC -- Replace players tables with views
# MAGIC DROP TABLE IF EXISTS nfl.players.players;
# MAGIC CREATE VIEW nfl.players.players AS SELECT * FROM nfl.landing.players;
# MAGIC
# MAGIC DROP TABLE IF EXISTS nfl.players.player_roles;
# MAGIC CREATE VIEW nfl.players.player_roles AS SELECT * FROM nfl.landing.player_roles;
# MAGIC
# MAGIC -- Replace rosters table with view
# MAGIC DROP TABLE IF EXISTS nfl.rosters.rosters;
# MAGIC CREATE VIEW nfl.rosters.rosters AS SELECT * FROM nfl.landing.rosters;
# MAGIC
# MAGIC -- Verify
# MAGIC SELECT 'players.players' as table_name, COUNT(*) FROM nfl.players.players
# MAGIC UNION ALL SELECT 'players.player_roles', COUNT(*) FROM nfl.players.player_roles
# MAGIC UNION ALL SELECT 'rosters.rosters', COUNT(*) FROM nfl.rosters.rosters;

# COMMAND ----------

# DBTITLE 1,Category A - PBP Schema
# MAGIC %sql
# MAGIC -- Replace pbp.play_by_play table with view
# MAGIC DROP TABLE IF EXISTS nfl.pbp.play_by_play;
# MAGIC CREATE VIEW nfl.pbp.play_by_play AS SELECT * FROM nfl.landing.play_by_play;
# MAGIC
# MAGIC -- Verify
# MAGIC SELECT 'pbp.play_by_play' as table_name, COUNT(*) as row_count FROM nfl.pbp.play_by_play;

# COMMAND ----------

# DBTITLE 1,Category B - Odds Schema
# MAGIC %sql
# MAGIC -- Replace odds tables with views
# MAGIC DROP TABLE IF EXISTS nfl.odds.game_odds;
# MAGIC CREATE VIEW nfl.odds.game_odds AS SELECT * FROM nfl.landing.game_odds;
# MAGIC
# MAGIC DROP TABLE IF EXISTS nfl.odds.odds_lines;
# MAGIC CREATE VIEW nfl.odds.odds_lines AS SELECT * FROM nfl.landing.odds_lines;
# MAGIC
# MAGIC DROP TABLE IF EXISTS nfl.odds.game_odds_latest;
# MAGIC CREATE VIEW nfl.odds.game_odds_latest AS SELECT * FROM nfl.landing.game_odds_latest;
# MAGIC
# MAGIC DROP TABLE IF EXISTS nfl.odds.odds_ingest_gaps;
# MAGIC CREATE VIEW nfl.odds.odds_ingest_gaps AS SELECT * FROM nfl.landing.odds_ingest_gaps;
# MAGIC
# MAGIC -- Verify
# MAGIC SELECT 'odds.game_odds' as table_name, COUNT(*) FROM nfl.odds.game_odds
# MAGIC UNION ALL SELECT 'odds.odds_lines', COUNT(*) FROM nfl.odds.odds_lines
# MAGIC UNION ALL SELECT 'odds.game_odds_latest', COUNT(*) FROM nfl.odds.game_odds_latest
# MAGIC UNION ALL SELECT 'odds.odds_ingest_gaps', COUNT(*) FROM nfl.odds.odds_ingest_gaps;

# COMMAND ----------

# DBTITLE 1,Category B - Predictions Schema
# MAGIC %sql
# MAGIC -- Replace predictions tables with views
# MAGIC DROP TABLE IF EXISTS nfl.predictions.game_predictions;
# MAGIC CREATE VIEW nfl.predictions.game_predictions AS SELECT * FROM nfl.landing.game_predictions;
# MAGIC
# MAGIC DROP TABLE IF EXISTS nfl.predictions.current_predictions;
# MAGIC CREATE VIEW nfl.predictions.current_predictions AS SELECT * FROM nfl.landing.current_predictions;
# MAGIC
# MAGIC DROP TABLE IF EXISTS nfl.predictions.prediction_grades;
# MAGIC CREATE VIEW nfl.predictions.prediction_grades AS SELECT * FROM nfl.landing.prediction_grades;
# MAGIC
# MAGIC DROP TABLE IF EXISTS nfl.predictions.prediction_rca;
# MAGIC CREATE VIEW nfl.predictions.prediction_rca AS SELECT * FROM nfl.landing.prediction_rca;
# MAGIC
# MAGIC -- Verify
# MAGIC SELECT 'predictions.game_predictions' as table_name, COUNT(*) FROM nfl.predictions.game_predictions
# MAGIC UNION ALL SELECT 'predictions.current_predictions', COUNT(*) FROM nfl.predictions.current_predictions
# MAGIC UNION ALL SELECT 'predictions.prediction_grades', COUNT(*) FROM nfl.predictions.prediction_grades
# MAGIC UNION ALL SELECT 'predictions.prediction_rca', COUNT(*) FROM nfl.predictions.prediction_rca;

# COMMAND ----------

# DBTITLE 1,Final Verification
# MAGIC %sql
# MAGIC -- Verify all tables are now views pointing to landing
# MAGIC SELECT 
# MAGIC   table_schema,
# MAGIC   table_name,
# MAGIC   table_type,
# MAGIC   CASE 
# MAGIC     WHEN table_type = 'VIEW' THEN '✓ View'
# MAGIC     WHEN table_type = 'MANAGED' THEN '⚠ Still Table'
# MAGIC     ELSE table_type
# MAGIC   END as status
# MAGIC FROM nfl.information_schema.tables
# MAGIC WHERE table_schema IN ('schedules', 'teams', 'players', 'rosters', 'pbp', 'odds', 'predictions')
# MAGIC   AND table_name IN (
# MAGIC     'games', 'teams', 'players', 'rosters', 'play_by_play', 'game_odds', 'game_predictions',
# MAGIC     'odds_lines', 'game_odds_latest', 'odds_ingest_gaps', 'player_roles',
# MAGIC     'current_predictions', 'prediction_grades', 'prediction_rca', 'nfelo_games', 'nfelo_ratings'
# MAGIC   )
# MAGIC ORDER BY table_schema, table_name;

# COMMAND ----------

# DBTITLE 1,Migration Complete Summary
# MAGIC %md
# MAGIC ## ✅ Migration Complete!
# MAGIC
# MAGIC Your NFL data architecture is now:
# MAGIC
# MAGIC ```
# MAGIC 📦 Landing (nfl.landing)
# MAGIC    ↓
# MAGIC 🔶 Bronze (nfl.bronze) - reads from landing
# MAGIC    ↓
# MAGIC 🔷 Silver (nfl.silver)
# MAGIC    ↓
# MAGIC 🏆 Gold (nfl.gold)
# MAGIC ```
# MAGIC
# MAGIC ### What Changed:
# MAGIC - **16 tables** moved to `nfl.landing` schema
# MAGIC - **16 views** created in old locations pointing to landing
# MAGIC - **Pipeline** reads from landing (already updated)
# MAGIC - **All consumers** (jobs, notebooks, dashboards) continue working
# MAGIC
# MAGIC ### Legacy Schemas:
# MAGIC The old schemas (schedules, teams, players, etc.) now only contain views. You can eventually deprecate these schemas and migrate consumers to use:
# MAGIC - `nfl.landing.*` for raw data
# MAGIC - `nfl.gold.*` for business metrics

# COMMAND ----------

