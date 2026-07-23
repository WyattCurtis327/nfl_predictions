from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.bronze.teams",
    comment="Bronze: Raw teams data with audit columns"
)
def bronze_teams():
    return (
        spark.read.table("nfl.landing.teams")
        .withColumn("_ingest_timestamp", F.current_timestamp())
        .withColumn("_source_schema", F.lit("landing"))
        .withColumn("_source_table", F.lit("teams"))
    )