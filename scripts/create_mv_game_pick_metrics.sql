-- Unity Catalog metric view: one row per graded game with ATS and O/U outcomes.
-- Deploy after prediction_grades has data.
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

dimensions:
  - game_id
  - season
  - week
  - gameday
  - away_abbr
  - home_abbr
  - predicted_winner_ats
  - predicted_total_pick
  - actual_winner
  - game_type

measures:
  - name: total_games
    expr: COUNT(*)
  - name: ats_wins
    expr: SUM(ats_covered)
  - name: ats_accuracy_pct
    expr: 100.0 * AVG(CAST(ats_covered AS DOUBLE))
  - name: ou_wins
    expr: SUM(over_under_covered)
  - name: ou_accuracy_pct
    expr: 100.0 * AVG(CAST(over_under_covered AS DOUBLE))
$$