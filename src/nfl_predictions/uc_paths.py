"""Unity Catalog path helpers for the medallion layout.

Layers (catalog ``nfl`` by default):

* **landing** — raw ingested domain tables (schedules, teams, PBP, odds, …)
* **bronze / silver / gold** — curated layers; prediction *outputs* live in **gold**

Job widgets still accept per-domain schema parameters for override flexibility, but
defaults all point at ``landing`` (domain) or ``gold`` (predictions).
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CATALOG = "nfl"

# Medallion layers
DEFAULT_LANDING_SCHEMA = "landing"
DEFAULT_BRONZE_SCHEMA = "bronze"
DEFAULT_SILVER_SCHEMA = "silver"
DEFAULT_GOLD_SCHEMA = "gold"

# Domain / product schema defaults (full path cutover targets)
DEFAULT_TEAMS_SCHEMA = DEFAULT_LANDING_SCHEMA
DEFAULT_SCHEDULES_SCHEMA = DEFAULT_LANDING_SCHEMA
DEFAULT_PBP_SCHEMA = DEFAULT_LANDING_SCHEMA
DEFAULT_ROSTERS_SCHEMA = DEFAULT_LANDING_SCHEMA
DEFAULT_PLAYERS_SCHEMA = DEFAULT_LANDING_SCHEMA
DEFAULT_ODDS_SCHEMA = DEFAULT_LANDING_SCHEMA
DEFAULT_PREDICTIONS_SCHEMA = DEFAULT_GOLD_SCHEMA


@dataclass(frozen=True)
class UcPaths:
    catalog: str = DEFAULT_CATALOG
    teams: str = DEFAULT_TEAMS_SCHEMA
    schedules: str = DEFAULT_SCHEDULES_SCHEMA
    pbp: str = DEFAULT_PBP_SCHEMA
    rosters: str = DEFAULT_ROSTERS_SCHEMA
    players: str = DEFAULT_PLAYERS_SCHEMA
    odds: str = DEFAULT_ODDS_SCHEMA
    predictions: str = DEFAULT_PREDICTIONS_SCHEMA
    bronze: str = DEFAULT_BRONZE_SCHEMA
    silver: str = DEFAULT_SILVER_SCHEMA

    def table(self, schema: str, table: str) -> str:
        return f"{self.catalog}.{schema}.{table}"

    def pbp_volume(self, *, subpath: str = "raw") -> str:
        return f"/Volumes/{self.catalog}/{self.pbp}/{subpath}"

    def teams_table(self) -> str:
        return self.table(self.teams, "teams")

    def nfelo_ratings_table(self) -> str:
        return self.table(self.teams, "nfelo_ratings")

    def nfelo_games_table(self) -> str:
        return self.table(self.teams, "nfelo_games")

    def schedules_games_table(self) -> str:
        return self.table(self.schedules, "games")

    def pbp_table(self) -> str:
        return self.table(self.pbp, "play_by_play")

    def rosters_table(self) -> str:
        return self.table(self.rosters, "rosters")

    def players_table(self) -> str:
        return self.table(self.players, "players")

    def player_roles_table(self) -> str:
        return self.table(self.players, "player_roles")

    def game_odds_table(self) -> str:
        return self.table(self.odds, "game_odds")

    def odds_lines_table(self) -> str:
        return self.table(self.odds, "odds_lines")

    def game_odds_latest_table(self) -> str:
        return self.table(self.odds, "game_odds_latest")

    def odds_ingest_gaps_table(self) -> str:
        return self.table(self.odds, "odds_ingest_gaps")

    def game_predictions_table(self) -> str:
        return self.table(self.predictions, "game_predictions")

    def current_predictions_table(self) -> str:
        return self.table(self.predictions, "current_predictions")

    def prediction_grades_table(self) -> str:
        return self.table(self.predictions, "prediction_grades")

    def prediction_rca_table(self) -> str:
        return self.table(self.predictions, "prediction_rca")

    def pick_miss_rca_view(self) -> str:
        return self.table(self.predictions, "pick_miss_rca")

    def game_pick_metrics_view(self) -> str:
        return self.table(self.predictions, "game_pick_metrics")

    def bronze_table(self, table: str) -> str:
        return self.table(self.bronze, table)

    def silver_table(self, table: str) -> str:
        return self.table(self.silver, table)

    def schema_map(self) -> dict[str, str]:
        """Map metadata JSON schema segments to configured schemas.

        Includes legacy domain names (teams, schedules, …) and medallion
        folder names (landing, gold) so both metadata layouts remap correctly.
        """
        return {
            # Legacy domain folders / table prefixes
            "teams": self.teams,
            "schedules": self.schedules,
            "pbp": self.pbp,
            "rosters": self.rosters,
            "players": self.players,
            "odds": self.odds,
            "predictions": self.predictions,
            # Medallion folders
            DEFAULT_LANDING_SCHEMA: self.schedules,
            DEFAULT_GOLD_SCHEMA: self.predictions,
            DEFAULT_BRONZE_SCHEMA: self.bronze,
            DEFAULT_SILVER_SCHEMA: self.silver,
        }

    def bootstrap_tables(self) -> list[str]:
        return [
            self.teams_table(),
            self.schedules_games_table(),
            self.pbp_table(),
            self.rosters_table(),
            self.players_table(),
            self.player_roles_table(),
            self.game_odds_table(),
            self.odds_lines_table(),
            self.game_odds_latest_table(),
            self.odds_ingest_gaps_table(),
        ]

    def prediction_tables(self) -> list[str]:
        return [
            self.game_predictions_table(),
            self.prediction_grades_table(),
            self.prediction_rca_table(),
        ]

    def metadata_tables(self) -> list[str]:
        return [*self.bootstrap_tables(), *self.prediction_tables()]


def bootstrap_tables_for_catalog(catalog: str = DEFAULT_CATALOG, **schemas: str) -> list[str]:
    return UcPaths(catalog=catalog, **schemas).bootstrap_tables()
