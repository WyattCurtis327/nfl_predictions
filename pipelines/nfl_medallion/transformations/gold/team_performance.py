from pyspark import pipelines as dp
from pyspark.sql import functions as F
from pyspark.sql.window import Window

@dp.materialized_view(
    name="nfl.gold.team_performance_by_season",
    comment="Gold: Team performance metrics aggregated by season"
)
def gold_team_performance():
    games = spark.read.table("nfl.silver.games")
    
    # Home games
    home_stats = (
        games
        .groupBy("season", "home_team")
        .agg(
            F.count("*").alias("home_games"),
            F.sum(F.when(F.col("home_score") > F.col("away_score"), 1).otherwise(0)).alias("home_wins"),
            F.avg("home_score").alias("avg_home_score"),
            F.avg("away_score").alias("avg_home_opponent_score")
        )
        .withColumnRenamed("home_team", "team")
    )
    
    # Away games
    away_stats = (
        games
        .groupBy("season", "away_team")
        .agg(
            F.count("*").alias("away_games"),
            F.sum(F.when(F.col("away_score") > F.col("home_score"), 1).otherwise(0)).alias("away_wins"),
            F.avg("away_score").alias("avg_away_score"),
            F.avg("home_score").alias("avg_away_opponent_score")
        )
        .withColumnRenamed("away_team", "team")
    )
    
    # Combine and calculate overall metrics
    return (
        home_stats.join(away_stats, ["season", "team"], "full_outer")
        .fillna(0)
        .withColumn("total_games", F.col("home_games") + F.col("away_games"))
        .withColumn("total_wins", F.col("home_wins") + F.col("away_wins"))
        .withColumn("win_percentage", F.col("total_wins") / F.col("total_games"))
        .withColumn("avg_points_scored", 
                   (F.col("avg_home_score") * F.col("home_games") + F.col("avg_away_score") * F.col("away_games")) / F.col("total_games"))
        .withColumn("avg_points_allowed", 
                   (F.col("avg_home_opponent_score") * F.col("home_games") + F.col("avg_away_opponent_score") * F.col("away_games")) / F.col("total_games"))
        .withColumn("point_differential", F.col("avg_points_scored") - F.col("avg_points_allowed"))
    )