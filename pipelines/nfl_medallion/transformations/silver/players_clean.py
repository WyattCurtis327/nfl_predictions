from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.silver.players",
    comment="Silver: Cleaned players data with data quality checks"
)
@dp.expect_or_drop("valid_player_id", "player_id IS NOT NULL")
@dp.expect_or_drop("valid_season", "season >= 1999 AND season <= 2030")
@dp.expect("valid_jersey", "jersey_number IS NULL OR (jersey_number >= 0 AND jersey_number <= 99)")
def silver_players():
    return (
        spark.read.table("nfl.bronze.players")
        .dropDuplicates(["player_id", "season", "week"])
        .withColumn("full_name_normalized", F.upper(F.trim(F.col("full_name"))))
        .withColumn("is_active", F.when(F.col("status") == "ACT", True).otherwise(False))
    )