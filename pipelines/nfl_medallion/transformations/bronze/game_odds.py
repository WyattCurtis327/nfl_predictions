from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.bronze.game_odds",
    comment="Bronze: Raw game odds data with audit columns"
)
def bronze_game_odds():
    return (
        spark.read.table("nfl.landing.game_odds")
        .withColumn("_ingest_timestamp", F.current_timestamp())
        .withColumn("_source_schema", F.lit("landing"))
        .withColumn("_source_table", F.lit("game_odds"))
    )