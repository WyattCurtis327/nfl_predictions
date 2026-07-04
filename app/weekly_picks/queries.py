"""SQL helpers for the weekly picks Streamlit app."""

from __future__ import annotations


def predictions_table(catalog: str, schema: str) -> str:
    return f"{catalog}.{schema}.game_predictions"


def list_season_weeks_sql(table: str) -> str:
    return f"""
        SELECT season, week, COUNT(*) AS games
        FROM {table}
        GROUP BY season, week
        ORDER BY season DESC, week DESC
    """


def describe_table_sql(table: str) -> str:
    return f"DESCRIBE TABLE {table}"


def latest_picks_sql(
    table: str,
    *,
    season: int,
    week: int,
    model_id: str = "monte_carlo",
    has_model_id: bool = True,
) -> str:
    safe_model = model_id.replace("'", "''")
    if has_model_id:
        model_filter = f"AND COALESCE(model_id, 'monte_carlo') = '{safe_model}'"
        model_select = "model_id,"
    else:
        model_filter = ""
        model_select = "'monte_carlo' AS model_id,"
    return f"""
        WITH ranked AS (
          SELECT
            *,
            ROW_NUMBER() OVER (
              PARTITION BY game_id
              ORDER BY predicted_at DESC, ingested_at DESC
            ) AS rn
          FROM {table}
          WHERE season = {int(season)}
            AND week = {int(week)}
            {model_filter}
        )
        SELECT
          game_id,
          {model_select}
          season,
          week,
          game_type,
          gameday,
          kickoff_et,
          away_abbr,
          home_abbr,
          away_spread,
          home_spread,
          total_line,
          bookmaker,
          proj_away_score,
          proj_home_score,
          proj_total,
          spread_pick,
          spread_confidence,
          total_pick,
          total_confidence,
          pick_threshold,
          market_blend,
          nfelo_blend,
          prediction_run_id,
          predicted_at,
          n_simulations
        FROM ranked
        WHERE rn = 1
        ORDER BY gameday, kickoff_et, game_id
    """