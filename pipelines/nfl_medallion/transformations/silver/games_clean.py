from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.silver.games",
    comment="Silver: Cleaned games data with data quality checks"
)
@dp.expect_or_drop("valid_game_id", "game_id IS NOT NULL")
@dp.expect_or_drop("valid_season", "season >= 1999 AND season <= 2030")
@dp.expect_or_drop("valid_teams", "home_team IS NOT NULL AND away_team IS NOT NULL")
@dp.expect("valid_scores", "(home_score IS NULL OR home_score >= 0) AND (away_score IS NULL OR away_score >= 0)")
def silver_games():
    return (
        spark.read.table("nfl.bronze.games")
        .dropDuplicates(["game_id"])
        .withColumn("gameday", F.to_date(F.col("gameday")))
        .withColumn("total_score", F.col("home_score") + F.col("away_score"))
        .withColumn("point_differential", F.col("home_score") - F.col("away_score"))
    )