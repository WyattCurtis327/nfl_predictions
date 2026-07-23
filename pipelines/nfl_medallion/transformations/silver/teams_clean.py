from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.silver.teams",
    comment="Silver: Cleaned teams data with data quality checks"
)
@dp.expect_or_drop("valid_season", "season >= 1999 AND season <= 2030")
@dp.expect_or_drop("valid_team", "team IS NOT NULL")
@dp.expect("consistent_naming", "full IS NOT NULL OR location IS NOT NULL")
def silver_teams():
    return (
        spark.read.table("nfl.bronze.teams")
        .dropDuplicates(["season", "team"])
        .withColumn("team_name_normalized", F.upper(F.trim(F.col("team"))))
    )