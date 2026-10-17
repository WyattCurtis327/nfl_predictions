import json
from pathlib import Path

from nfl_predictions.uc_paths import UcPaths
from nfl_predictions.uc_schema import (
    apply_metadata,
    build_apply_statements,
    column_comment_sql,
    escape_sql_string,
    filter_schema_files,
    list_schema_files,
    remap_table_catalog,
    remap_table_reference,
    resolve_schema_directory,
    schema_dir_candidates,
    table_comment_sql,
    write_manifest_from_directory,
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
    assert remap_table_catalog("nfl.landing.game_odds", "prod_nfl") == "prod_nfl.landing.game_odds"


def test_build_apply_statements_honors_schema_map():
    # landing/* tables remap via the shared landing schema (schedules widget).
    paths = UcPaths(catalog="prod", schedules="raw_zone")
    metadata = {
        "table": "nfl.landing.game_odds",
        "comment": "",
        "columns": [{"name": "game_id", "comment": "Game key"}],
    }

    _, column_sql = build_apply_statements(
        metadata,
        catalog=paths.catalog,
        schema_map=paths.schema_map(),
    )

    assert column_sql[0][1].startswith("ALTER TABLE prod.raw_zone.game_odds")


def test_build_apply_statements():
    metadata = {
        "table": "nfl.landing.game_odds",
        "comment": "Closing lines",
        "columns": [
            {"name": "game_id", "comment": "Game key"},
            {"name": "season", "comment": ""},
        ],
    }

    table_sql, column_sql = build_apply_statements(metadata, catalog="nfl")

    assert table_sql == table_comment_sql("nfl.landing.game_odds", "Closing lines")
    assert len(column_sql) == 1
    assert column_sql[0][0] == "game_id"


def test_column_comment_sql_quotes_special_column_names():
    sql = column_comment_sql("nfl.landing.games", "_source_file", "Source path")
    assert "ALTER TABLE nfl.landing.games ALTER COLUMN `_source_file` COMMENT 'Source path'" == sql


def test_apply_metadata_skips_missing_columns(tmp_path: Path):
    metadata_path = tmp_path / "nfl" / "odds" / "game_odds.json"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps(
            {
                "table": "nfl.landing.game_odds",
                "comment": "",
                "columns": [
                    {"name": "game_id", "comment": "Game key"},
                    {"name": "missing_col", "comment": "Should skip"},
                ],
            }
        ),
        encoding="utf-8",
    )

    spark = _FakeSpark({"nfl.landing.game_odds": ["game_id"]})
    summary = apply_metadata(spark, json.loads(metadata_path.read_text()), catalog="nfl")

    assert summary.column_comments_applied == 1
    assert summary.column_comments_skipped == 1
    assert len(spark.sql_calls) == 1


def test_apply_metadata_skips_missing_table_when_requested():
    spark = _FakeSpark({})
    metadata = {
        "table": "nfl.gold.prediction_grades",
        "comment": "",
        "columns": [{"name": "game_id", "comment": "Game key"}],
    }

    summary = apply_metadata(
        spark,
        metadata,
        catalog="nfl",
        skip_missing_tables=True,
    )

    assert summary.errors == []
    assert summary.column_comments_applied == 0
    assert spark.sql_calls == []


def test_filter_schema_files_limits_to_one_schema(tmp_path: Path):
    predictions = tmp_path / "nfl" / "predictions" / "game_predictions.json"
    teams = tmp_path / "nfl" / "teams" / "teams.json"
    predictions.parent.mkdir(parents=True)
    teams.parent.mkdir(parents=True)
    predictions.write_text("{}", encoding="utf-8")
    teams.write_text("{}", encoding="utf-8")

    filtered = filter_schema_files(list_schema_files(tmp_path), only_canonical_schema="predictions")
    assert filtered == [predictions]


def test_write_manifest_from_directory(tmp_path: Path):
    table_path = tmp_path / "nfl" / "predictions" / "game_predictions.json"
    table_path.parent.mkdir(parents=True)
    table_path.write_text(
        json.dumps({"table": "nfl.gold.game_predictions", "columns": []}),
        encoding="utf-8",
    )

    manifest_path = write_manifest_from_directory(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["catalog"] == "nfl"
    assert manifest["tables"] == ["nfl.gold.game_predictions"]
    assert manifest["files"] == ["nfl/predictions/game_predictions.json"]


def test_schema_dir_candidates_adds_workspace_alias():
    candidates = schema_dir_candidates("/Users/me/.bundle/nfl_predictions/prod/files/resources/schema")
    assert candidates[0].as_posix() == "/Users/me/.bundle/nfl_predictions/prod/files/resources/schema"
    assert candidates[1].as_posix() == "/Workspace/Users/me/.bundle/nfl_predictions/prod/files/resources/schema"


def test_resolve_schema_directory_tries_extra_candidates(tmp_path: Path):
    primary = tmp_path / "missing"
    resolved_root = tmp_path / "bundle" / "resources" / "schema"
    table_path = resolved_root / "nfl" / "teams" / "teams.json"
    table_path.parent.mkdir(parents=True)
    table_path.write_text("{}", encoding="utf-8")

    resolved = resolve_schema_directory(primary, extra_candidates=[resolved_root])
    assert resolved == resolved_root


def test_list_schema_files_excludes_manifest(tmp_path: Path):
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    table_path = tmp_path / "nfl" / "teams" / "teams.json"
    table_path.parent.mkdir(parents=True)
    table_path.write_text("{}", encoding="utf-8")

    files = list_schema_files(tmp_path)
    assert files == [table_path]