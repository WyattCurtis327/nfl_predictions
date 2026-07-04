# Databricks notebook source
# MAGIC %md
# MAGIC # Build player dimensions
# MAGIC Creates `nfl.players.players` and `nfl.players.player_roles` from rosters + PBP.

# COMMAND ----------

from nfl_predictions.uc_paths import (
    DEFAULT_CATALOG,
    DEFAULT_PBP_SCHEMA,
    DEFAULT_PLAYERS_SCHEMA,
    DEFAULT_ROSTERS_SCHEMA,
    UcPaths,
)

dbutils.widgets.text("catalog", DEFAULT_CATALOG, "Unity Catalog")
dbutils.widgets.text("players_schema", DEFAULT_PLAYERS_SCHEMA, "Players schema")
dbutils.widgets.text("rosters_schema", DEFAULT_ROSTERS_SCHEMA, "Rosters schema")
dbutils.widgets.text("pbp_schema", DEFAULT_PBP_SCHEMA, "PBP schema")

paths = UcPaths(
    catalog=dbutils.widgets.get("catalog"),
    players=dbutils.widgets.get("players_schema"),
    rosters=dbutils.widgets.get("rosters_schema"),
    pbp=dbutils.widgets.get("pbp_schema"),
)
players_table = paths.players_table()
roles_table = paths.player_roles_table()
rosters_table = paths.rosters_table()
pbp_table = paths.pbp_table()

# COMMAND ----------

from nfl_predictions.core import build_player_dimension, extract_pbp_player_roles
from nfl_predictions.metadata import stamp_dataframe
from nfl_predictions.spark_io import write_delta_table

rosters_pdf = spark.table(rosters_table).toPandas()

if spark.catalog.tableExists(pbp_table):
    pbp_pdf = spark.table(pbp_table).toPandas()
    print(f"PBP rows loaded: {len(pbp_pdf):,}")
else:
    pbp_pdf = __import__("pandas").DataFrame()
    print(f"PBP table {pbp_table} not found; player_roles will be empty")

players_df = build_player_dimension(rosters_pdf)
roles_df = extract_pbp_player_roles(pbp_pdf)

players_pdf = stamp_dataframe(players_df, source_file=rosters_table)
roles_pdf = stamp_dataframe(roles_df, source_file=pbp_table if not pbp_pdf.empty else rosters_table)

print(f"players: {len(players_pdf):,} rows")
print(f"name collisions disambiguated: {int(players_pdf['name_collision'].sum())}")
print(f"player_roles: {len(roles_pdf):,} rows")

# COMMAND ----------

write_delta_table(spark, players_pdf, players_table, dedupe_keys=["player_id"])
write_delta_table(
    spark,
    roles_pdf,
    roles_table,
    dedupe_keys=["game_id", "play_id", "player_id", "role"],
)

display(spark.table(players_table).limit(20))