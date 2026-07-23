from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.bronze.play_by_play",
    comment="Bronze: Raw play-by-play data with audit columns"
)
def bronze_play_by_play():
    return (
        spark.read.table("nfl.landing.play_by_play")
        .withColumn("_ingest_timestamp", F.current_timestamp())
        .withColumn("_source_schema", F.lit("landing"))
        .withColumn("_source_table", F.lit("play_by_play"))
    )