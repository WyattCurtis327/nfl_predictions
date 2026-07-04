import json
from pathlib import Path

from nfl_predictions.uc_paths import UcPaths
from nfl_predictions.uc_schema import (
    apply_metadata,
    build_apply_statements,
    column_comment_sql,
    escape_sql_string,
    list_schema_files,
    remap_table_catalog,
    remap_table_reference,
    table_comment_sql,
)


class _FakeField:
    def __init__(self, name: str):
        self.name = name


class _FakeCatalog:
    def __init__(self, spark: "_FakeSpark"):
        self._spark = spark

    def tableExists(self, name: str) -> bool:
        return name in self._spark.tables


class _FakeSpark:
    def __init__(self, tables: dict[str, list[str]]):
        self.tables = tables
        self.catalog = _FakeCatalog(self)
        self.sql_calls: list[str] = []

    def table(self, name: str):
        fields = [_FakeField(column) for column in self.tables[name]]
        return type("SchemaTable", (), {"schema": type("Schema", (), {"fields": fields})()})()

    def sql(self, statement: str):
        self.sql_calls.append(statement)


def test_escape_sql_string_doubles_single_quotes():
    assert escape_sql_string("player's role") == "player''s role"


def test_remap_table_catalog():
    assert remap_table_catalog("nfl.odds.game_odds", "prod_nfl") == "prod_nfl.odds.game_odds"


def test_build_apply_statements_honors_schema_map():
    paths = UcPaths(catalog="prod", odds="odds_data")
    metadata = {
        "table": "nfl.odds.game_odds",
        "comment": "",
        "columns": [{"name": "game_id", "comment": "Game key"}],
    }

    _, column_sql = build_apply_statements(
        metadata,
        catalog=paths.catalog,
        schema_map=paths.schema_map(),
    )

    assert column_sql[0][1].startswith("ALTER TABLE prod.odds_data.game_odds")


def test_build_apply_statements():
    metadata = {
        "table": "nfl.odds.game_odds",
        "comment": "Closing lines",
        "columns": [
            {"name": "game_id", "comment": "Game key"},
            {"name": "season", "comment": ""},
        ],
    }

    table_sql, column_sql = build_apply_statements(metadata, catalog="nfl")

    assert table_sql == table_comment_sql("nfl.odds.game_odds", "Closing lines")
    assert len(column_sql) == 1
    assert column_sql[0][0] == "game_id"


def test_column_comment_sql_quotes_special_column_names():
    sql = column_comment_sql("nfl.schedules.games", "_source_file", "Source path")
    assert "ALTER TABLE nfl.schedules.games ALTER COLUMN `_source_file` COMMENT 'Source path'" == sql


def test_apply_metadata_skips_missing_columns(tmp_path: Path):
    metadata_path = tmp_path / "nfl" / "odds" / "game_odds.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps(
            {
                "table": "nfl.odds.game_odds",
                "comment": "",
                "columns": [
                    {"name": "game_id", "comment": "Game key"},
                    {"name": "missing_col", "comment": "Should skip"},
                ],
            }
        ),
        encoding="utf-8",
    )

    spark = _FakeSpark({"nfl.odds.game_odds": ["game_id"]})
    summary = apply_metadata(spark, json.loads(metadata_path.read_text()), catalog="nfl")

    assert summary.column_comments_applied == 1
    assert summary.column_comments_skipped == 1
    assert len(spark.sql_calls) == 1


def test_list_schema_files_excludes_manifest(tmp_path: Path):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    table_path = tmp_path / "nfl" / "teams" / "teams.json"
    table_path.parent.mkdir(parents=True)
    table_path.write_text("{}", encoding="utf-8")

    files = list_schema_files(tmp_path)
    assert files == [table_path]