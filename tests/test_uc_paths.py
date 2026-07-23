from nfl_predictions.uc_paths import (
    DEFAULT_GOLD_SCHEMA,
    DEFAULT_LANDING_SCHEMA,
    UcPaths,
    bootstrap_tables_for_catalog,
)
from nfl_predictions.uc_schema import remap_table_reference


def test_uc_paths_defaults_use_medallion_layers():
    paths = UcPaths()

    assert paths.schedules_games_table() == f"nfl.{DEFAULT_LANDING_SCHEMA}.games"
    assert paths.pbp_table() == f"nfl.{DEFAULT_LANDING_SCHEMA}.play_by_play"
    assert paths.game_predictions_table() == f"nfl.{DEFAULT_GOLD_SCHEMA}.game_predictions"
    assert paths.pbp_volume() == f"/Volumes/nfl/{DEFAULT_LANDING_SCHEMA}/raw"


def test_uc_paths_builds_volume_and_tables():
    paths = UcPaths(catalog="prod", pbp="pbp_data", odds="odds_data")

    assert paths.pbp_volume() == "/Volumes/prod/pbp_data/raw"
    assert paths.game_odds_table() == "prod.odds_data.game_odds"
    assert paths.schedules_games_table() == "prod.landing.games"
    assert paths.game_predictions_table() == "prod.gold.game_predictions"


def test_bootstrap_tables_for_catalog():
    tables = bootstrap_tables_for_catalog("prod", odds="odds_data")

    assert "prod.odds_data.game_odds" in tables
    assert "prod.landing.teams" in tables


def test_remap_table_reference_updates_catalog_and_schema():
    paths = UcPaths(catalog="prod", schedules="schedule_data")
    mapped = remap_table_reference(
        "nfl.landing.games",
        catalog=paths.catalog,
        schema_map=paths.schema_map(),
    )

    assert mapped == "prod.schedule_data.games"


def test_remap_gold_predictions_schema():
    paths = UcPaths(catalog="prod", predictions="analytics")
    mapped = remap_table_reference(
        "nfl.gold.game_predictions",
        catalog=paths.catalog,
        schema_map=paths.schema_map(),
    )

    assert mapped == "prod.analytics.game_predictions"
