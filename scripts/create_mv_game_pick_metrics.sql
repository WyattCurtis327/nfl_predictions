-- Unity Catalog metric view: one row per graded game with ATS and O/U outcomes.
-- Deploy: python scripts/deploy_mv_game_pick_metrics.py
CREATE OR REPLACE VIEW nfl.predictions.game_pick_metrics
WITH METRICS
LANGUAGE YAML
AS
$$
version: 1.1

source: |-
  SELECT
    g.game_id,
    g.season,
    g.week,
    g.game_type,
    g.gameday,
    g.away_abbr,
    g.home_abbr,
    g.spread_pick AS predicted_ats_pick,
    CASE
      WHEN g.spread_pick = g.away_abbr THEN g.away_abbr
      WHEN g.spread_pick = g.home_abbr THEN g.home_abbr
      ELSE NULL
    END AS predicted_winner_ats,
    g.total_pick AS predicted_total_pick,
    CAST(g.spread_correct AS INT) AS ats_covered,
    CAST(g.total_correct AS INT) AS over_under_covered,
    g.actual_winner,
    g.away_spread,
    g.home_spread,
    g.total_line,
    g.spread_confidence,
    g.total_confidence,
    g.graded_at
  FROM nfl.predictions.prediction_grades g
  WHERE g.game_type IN ('REG', 'WC', 'DIV', 'CON', 'SB')

comment: "Graded NFL pick accuracy metrics. One row per graded game with ATS and over/under outcomes from prediction_grades."

dimensions:
  - name: game_id
    expr: game_id
    display_name: Game ID

  - name: season
    expr: season
    display_name: Season

  - name: week
    expr: week
    display_name: Week

  - name: gameday
    expr: TO_DATE(gameday)
    display_name: Game Date

  - name: away_abbr
    expr: away_abbr
    display_name: Away Team

  - name: home_abbr
    expr: home_abbr
    display_name: Home Team

  - name: predicted_winner_ats
    expr: predicted_winner_ats
    display_name: Predicted ATS Winner

  - name: predicted_total_pick
    expr: predicted_total_pick
    display_name: Predicted Total Pick

  - name: actual_winner
    expr: actual_winner
    display_name: Actual Winner

  - name: game_type
    expr: game_type
    display_name: Game Type

measures:
  - name: total_games
    expr: COUNT(*)
    display_name: Total Games

  - name: ats_wins
    expr: SUM(ats_covered)
    display_name: ATS Wins

  - name: ats_accuracy_pct
    expr: 100.0 * AVG(CAST(ats_covered AS DOUBLE))
    display_name: ATS Accuracy %

  - name: ou_wins
    expr: SUM(over_under_covered)
    display_name: Over/Under Wins

  - name: ou_accuracy_pct
    expr: 100.0 * AVG(CAST(over_under_covered AS DOUBLE))
    display_name: Over/Under Accuracy %
$$