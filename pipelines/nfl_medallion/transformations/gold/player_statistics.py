from pyspark import pipelines as dp
from pyspark.sql import functions as F

@dp.materialized_view(
    name="nfl.gold.player_statistics_by_season",
    comment="Gold: Player statistics aggregated by season and team"
)
def gold_player_statistics():
    players = spark.read.table("nfl.silver.players")
    
    return (
        players
        .groupBy("season", "team", "position")
        .agg(
            F.count("player_id").alias("total_players"),
            F.countDistinct("player_id").alias("unique_players"),
            F.sum(F.when(F.col("is_active"), 1).otherwise(0)).alias("active_players"),
            F.avg("jersey_number").alias("avg_jersey_number")
        )
        .withColumn("active_rate", F.col("active_players") / F.col("total_players"))
        .orderBy("season", "team", "position")
    )