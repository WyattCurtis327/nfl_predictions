from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.bronze.rosters",
    comment="Bronze: Raw rosters data with audit columns"
)
def bronze_rosters():
    return (
        spark.read.table("nfl.landing.rosters")
        .withColumn("_ingest_timestamp", F.current_timestamp())
        .withColumn("_source_schema", F.lit("landing"))
        .withColumn("_source_table", F.lit("rosters"))
    )