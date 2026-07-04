-- Add model_id for multi-model prediction stack (idempotent).
ALTER TABLE {catalog}.{predictions_schema}.game_predictions
ADD COLUMN IF NOT EXISTS model_id STRING
COMMENT 'Prediction model family (monte_carlo, poisson, elo, epa_margin, line_relative, shrinkage_profile, situational_total, ensemble)';

ALTER TABLE {catalog}.{predictions_schema}.prediction_grades
ADD COLUMN IF NOT EXISTS model_id STRING
COMMENT 'Prediction model family that produced the graded pick';