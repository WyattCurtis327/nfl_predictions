from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.bronze.games",
    comment="Bronze: Raw games data with audit columns"
)
def bronze_games():
    return (
        spark.read.table("nfl.landing.games")
        .withColumn("_ingest_timestamp", F.current_timestamp())
        .withColumn("_source_schema", F.lit("landing"))
        .withColumn("_source_table", F.lit("games"))
    )