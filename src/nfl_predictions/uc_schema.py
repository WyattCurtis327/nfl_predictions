"""Apply Unity Catalog table and column comments from local schema metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from nfl_predictions.uc_paths import DEFAULT_CATALOG, UcPaths, bootstrap_tables_for_catalog

DEFAULT_BOOTSTRAP_TABLES = bootstrap_tables_for_catalog(DEFAULT_CATALOG)


@dataclass
class ApplySummary:
    table: str
    table_comment_applied: bool = False
    column_comments_applied: int = 0
    column_comments_skipped: int = 0
    errors: list[str] = field(default_factory=list)


def escape_sql_string(value: str) -> str:
    return value.replace("'", "''")


def quote_column(name: str) -> str:
    return f"`{name.replace('`', '``')}`"


def remap_table_reference(
    full_name: str,
    *,
    catalog: str,
    schema_map: dict[str, str] | None = None,
) -> str:
    parts = full_name.split(".", 2)
    if len(parts) != 3:
        return full_name
    _, schema, table = parts
    mapped_schema = (schema_map or {}).get(schema, schema)
    return f"{catalog}.{mapped_schema}.{table}"


def remap_table_catalog(full_name: str, catalog: str) -> str:
    return remap_table_reference(full_name, catalog=catalog)


def load_metadata_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_dir_candidates(schema_dir: Path | str) -> list[Path]:
    """Return filesystem paths to try for a bundle or workspace schema directory."""
    text = str(schema_dir).strip()
    if not text:
        return []

    candidates: list[Path] = [Path(text)]
    if text.startswith("/Users/"):
        candidates.append(Path(f"/Workspace{text}"))
    elif text.startswith("/Workspace/Users/"):
        candidates.append(Path(text.removeprefix("/Workspace")))
    return candidates


def list_schema_files(schema_dir: Path | str) -> list[Path]:
    for root in schema_dir_candidates(schema_dir):
        if not root.exists():
            continue
        return sorted(
            path for path in root.rglob("*.json") if path.name != "manifest.json"
        )
    return []


def resolve_schema_directory(
    schema_dir: Path | str,
    *,
    extra_candidates: list[Path | str] | None = None,
) -> Path:
    """Return the first schema directory that contains metadata JSON files."""
    candidates: list[Path] = []
    for value in [schema_dir, *(extra_candidates or [])]:
        candidates.extend(schema_dir_candidates(value))

    seen: set[str] = set()
    tried: list[str] = []
    for root in candidates:
        key = root.as_posix()
        if key in seen:
            continue
        seen.add(key)
        tried.append(key)
        files = list_schema_files(root)
        if files:
            return root

    raise FileNotFoundError(
        f"No schema metadata files found. Tried: {tried}"
    )


def table_comment_sql(table: str, comment: str) -> str:
    escaped = escape_sql_string(comment)
    return f"COMMENT ON TABLE {table} IS '{escaped}'"


def column_comment_sql(table: str, column: str, comment: str) -> str:
    escaped = escape_sql_string(comment)
    return f"ALTER TABLE {table} ALTER COLUMN {quote_column(column)} COMMENT '{escaped}'"


def build_apply_statements(
    metadata: dict,
    *,
    catalog: str,
    schema_map: dict[str, str] | None = None,
) -> tuple[str, list[tuple[str, str]]]:
    """Return table comment SQL (or empty) and column comment SQL statements."""
    table_name = remap_table_reference(metadata["table"], catalog=catalog, schema_map=schema_map)
    statements: list[tuple[str, str]] = []

    table_sql = ""
    table_comment = (metadata.get("comment") or "").strip()
    if table_comment:
        table_sql = table_comment_sql(table_name, table_comment)

    for column in metadata.get("columns", []):
        name = column.get("name")
        comment = (column.get("comment") or "").strip()
        if not name or not comment:
            continue
        statements.append((name, column_comment_sql(table_name, name, comment)))

    return table_sql, statements


def apply_metadata(
    spark,
    metadata: dict,
    *,
    catalog: str,
    schema_map: dict[str, str] | None = None,
    only_existing_columns: bool = True,
    skip_missing_tables: bool = False,
) -> ApplySummary:
    """Apply table and column comments for one metadata document."""
    table_name = remap_table_reference(metadata["table"], catalog=catalog, schema_map=schema_map)
    summary = ApplySummary(table=table_name)

    if only_existing_columns and spark.catalog.tableExists(table_name):
        existing_columns = {field.name for field in spark.table(table_name).schema.fields}
    elif spark.catalog.tableExists(table_name):
        existing_columns = None
    elif skip_missing_tables:
        return summary
    else:
        summary.errors.append(f"table not found: {table_name}")
        return summary

    table_sql, column_statements = build_apply_statements(
        metadata,
        catalog=catalog,
        schema_map=schema_map,
    )
    if table_sql:
        try:
            spark.sql(table_sql)
            summary.table_comment_applied = True
        except Exception as exc:  # noqa: BLE001 - surface UC errors to job logs
            summary.errors.append(f"table comment failed: {exc}")

    for column_name, sql in column_statements:
        if existing_columns is not None and column_name not in existing_columns:
            summary.column_comments_skipped += 1
            continue
        try:
            spark.sql(sql)
            summary.column_comments_applied += 1
        except Exception as exc:  # noqa: BLE001
            summary.column_comments_skipped += 1
            summary.errors.append(f"{column_name}: {exc}")

    return summary


def filter_schema_files(
    files: list[Path],
    *,
    only_canonical_schema: str | None = None,
) -> list[Path]:
    """Keep metadata files under ``nfl/<schema>/`` when filtering."""
    if not only_canonical_schema:
        return files
    needle = f"/nfl/{only_canonical_schema}/"
    return [
        path
        for path in files
        if needle in path.as_posix().lower()
    ]


def write_manifest_from_directory(schema_dir: Path | str) -> Path:
    """Rebuild manifest.json from all metadata files in a schema directory."""
    root = Path(schema_dir)
    files = list_schema_files(root)
    tables: list[str] = []
    rel_files: list[str] = []
    catalog = DEFAULT_CATALOG

    for path in files:
        metadata = load_metadata_file(path)
        table_name = metadata.get("table")
        if table_name:
            tables.append(table_name)
            if "." in table_name:
                catalog = table_name.split(".", 1)[0]
        rel_files.append(path.relative_to(root).as_posix())

    manifest = {
        "catalog": catalog,
        "tables": tables,
        "files": rel_files,
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def apply_schema_directory(
    spark,
    schema_dir: Path | str,
    *,
    catalog: str = DEFAULT_CATALOG,
    schema_map: dict[str, str] | None = None,
    paths: UcPaths | None = None,
    only_canonical_schema: str | None = None,
    skip_missing_tables: bool = False,
    extra_schema_dir_candidates: list[Path | str] | None = None,
) -> list[ApplySummary]:
    """Apply all schema metadata JSON files under a directory."""
    root = resolve_schema_directory(schema_dir, extra_candidates=extra_schema_dir_candidates)
    summaries: list[ApplySummary] = []
    resolved_catalog = paths.catalog if paths else catalog
    resolved_schema_map = paths.schema_map() if paths else schema_map

    for path in filter_schema_files(list_schema_files(root), only_canonical_schema=only_canonical_schema):
        metadata = load_metadata_file(path)
        summaries.append(
            apply_metadata(
                spark,
                metadata,
                catalog=resolved_catalog,
                schema_map=resolved_schema_map,
                skip_missing_tables=skip_missing_tables,
            )
        )

    return summaries