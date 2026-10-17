from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.silver.game_odds",
    comment="Silver: Cleaned game odds data with data quality checks"
)
@dp.expect_or_drop("valid_game_id", "game_id IS NOT NULL")
@dp.expect_or_drop("valid_teams", "home_team IS NOT NULL AND away_team IS NOT NULL")
@dp.expect("valid_odds", "spread_line IS NOT NULL OR total_line IS NOT NULL")
def silver_game_odds():
    return (
        spark.read.table("nfl.bronze.game_odds")
        .dropDuplicates(["game_id", "bookmaker"])
        .withColumn("gameday", F.to_date(F.col("gameday")))
        .withColumn("has_spread", F.col("spread_line").isNotNull())
        .withColumn("has_total", F.col("total_line").isNotNull())
        .withColumn("has_moneyline", F.col("home_moneyline").isNotNull() | F.col("away_moneyline").isNotNull())
    )