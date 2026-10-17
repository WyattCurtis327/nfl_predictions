"""SQL and transforms for team net offensive/defensive ratings."""

from __future__ import annotations

import pandas as pd

DEFAULT_GAME_TYPES = ("REG", "WC", "DIV", "CON", "SB")


def pbp_season_weeks_sql(table: str, *, game_types: tuple[str, ...] = DEFAULT_GAME_TYPES) -> str:
    quoted = ", ".join(f"'{value}'" for value in game_types)
    return f"""
        SELECT season, week, COUNT(DISTINCT game_id) AS games
        FROM {table}
        WHERE season_type IN ({quoted})
        GROUP BY season, week
        ORDER BY season DESC, week ASC
    """


def team_scoring_sql(
    table: str,
    *,
    season: int,
    weeks: list[int],
    game_types: tuple[str, ...] = DEFAULT_GAME_TYPES,
) -> str:
    if not weeks:
        raise ValueError("Select at least one week")
    week_list = ", ".join(str(int(week)) for week in sorted(set(weeks)))
    quoted_types = ", ".join(f"'{value}'" for value in game_types)
    return f"""
        WITH games AS (
          SELECT
            game_id,
            season,
            week,
            home_team,
            away_team,
            MAX(total_home_score) AS home_score,
            MAX(total_away_score) AS away_score
          FROM {table}
          WHERE season = {int(season)}
            AND week IN ({week_list})
            AND season_type IN ({quoted_types})
          GROUP BY game_id, season, week, home_team, away_team
        ),
        team_games AS (
          SELECT home_team AS team, home_score AS points_for, away_score AS points_against
          FROM games
          UNION ALL
          SELECT away_team AS team, away_score AS points_for, home_score AS points_against
          FROM games
        )
        SELECT
          team,
          COUNT(*) AS games,
          AVG(points_for) AS points_for_mean,
          AVG(points_against) AS points_against_mean
        FROM team_games
        GROUP BY team
        ORDER BY team
    """


def add_net_ratings(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute league-relative net offensive and defensive ratings."""
    if frame.empty:
        return frame.assign(
            net_offensive=pd.Series(dtype="float64"),
            net_defensive=pd.Series(dtype="float64"),
            league_points_for=pd.Series(dtype="float64"),
            league_points_against=pd.Series(dtype="float64"),
        )

    ratings = frame.copy()
    league_pf = float(ratings["points_for_mean"].mean())
    league_pa = float(ratings["points_against_mean"].mean())
    ratings["league_points_for"] = round(league_pf, 2)
    ratings["league_points_against"] = round(league_pa, 2)
    ratings["net_offensive"] = ratings["points_for_mean"] - league_pf
    ratings["net_defensive"] = league_pa - ratings["points_against_mean"]
    return ratings.round(
        {
            "points_for_mean": 2,
            "points_against_mean": 2,
            "net_offensive": 2,
            "net_defensive": 2,
        }
    )