from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.gold.game_summaries",
    comment="Gold: Enhanced game summaries with odds and predictions"
)
def gold_game_summaries():
    games = spark.read.table("nfl.silver.games")
    odds = spark.read.table("nfl.silver.game_odds")
    
    # Get average odds per game across bookmakers
    odds_avg = (
        odds
        .groupBy("game_id")
        .agg(
            F.avg("spread_line").alias("avg_spread"),
            F.avg("total_line").alias("avg_total"),
            F.count("*").alias("num_bookmakers")
        )
    )
    
    return (
        games
        .join(odds_avg, "game_id", "left")
        .withColumn("is_upset", 
                   F.when((F.col("avg_spread") > 0) & (F.col("point_differential") > 0), True)
                   .when((F.col("avg_spread") < 0) & (F.col("point_differential") < 0), True)
                   .otherwise(False))
        .withColumn("beat_spread", 
                   F.abs(F.col("point_differential")) > F.abs(F.col("avg_spread")))
        .withColumn("over_under_result",
                   F.when(F.col("total_score") > F.col("avg_total"), "Over")
                   .when(F.col("total_score") < F.col("avg_total"), "Under")
                   .otherwise("Push"))
        .select(
            "game_id", "season", "week", "game_type", "gameday",
            "home_team", "away_team", "home_score", "away_score",
            "total_score", "point_differential",
            "avg_spread", "avg_total", "num_bookmakers",
            "is_upset", "beat_spread", "over_under_result"
        )
    )