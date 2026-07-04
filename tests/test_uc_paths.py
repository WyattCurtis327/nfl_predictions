from nfl_predictions.uc_paths import UcPaths, bootstrap_tables_for_catalog
from nfl_predictions.uc_schema import remap_table_reference


def test_uc_paths_builds_volume_and_tables():
    paths = UcPaths(catalog="prod", pbp="pbp_data", odds="odds_data")

    assert paths.pbp_volume() == "/Volumes/prod/pbp_data/raw"
    assert paths.game_odds_table() == "prod.odds_data.game_odds"
    assert paths.schedules_games_table() == "prod.schedules.games"


def test_bootstrap_tables_for_catalog():
    tables = bootstrap_tables_for_catalog("prod", odds="odds_data")

    assert "prod.odds_data.game_odds" in tables
    assert "prod.teams.teams" in tables


def test_remap_table_reference_updates_catalog_and_schema():
    paths = UcPaths(catalog="prod", schedules="schedule_data")
    mapped = remap_table_reference(
        "nfl.schedules.games",
        catalog=paths.catalog,
        schema_map=paths.schema_map(),
    )

    assert mapped == "prod.schedule_data.games"