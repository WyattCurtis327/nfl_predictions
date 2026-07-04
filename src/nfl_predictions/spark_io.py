"""Helpers for writing pandas DataFrames to Spark on serverless."""

from __future__ import annotations

import pandas as pd


def _nullable_object_is_boolean(series: pd.Series) -> bool:
    """True when an object column only contains bool values and nulls."""
    non_null = series.dropna()
    if non_null.empty:
        return False
    return bool(non_null.map(type).eq(bool).all())


def prepare_pandas_for_spark(pdf: pd.DataFrame) -> pd.DataFrame:
    """Coerce ambiguous pandas dtypes so Spark Connect can infer a schema."""
    frame = pdf.copy()

    for column in frame.columns:
        series = frame[column]
        if series.isna().all():
            frame[column] = series.astype("string")
        elif pd.api.types.is_bool_dtype(series.dtype):
            frame[column] = series.astype("boolean")
        elif series.dtype == object and _nullable_object_is_boolean(series):
            frame[column] = series.astype("boolean")
        elif series.dtype == object:
            frame[column] = series.astype("string")
        elif pd.api.types.is_datetime64_any_dtype(series.dtype):
            frame[column] = pd.to_datetime(series, utc=True, errors="coerce")

    return frame


def pandas_to_spark(spark, pdf: pd.DataFrame):
    prepared = prepare_pandas_for_spark(pdf)
    return spark.createDataFrame(prepared)


def dedupe_pandas(pdf: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Keep the latest row per natural key."""
    available = [key for key in keys if key in pdf.columns]
    if not available or pdf.empty:
        return pdf.reset_index(drop=True)
    return pdf.drop_duplicates(subset=available, keep="last").reset_index(drop=True)


def write_delta_table(
    spark,
    pdf: pd.DataFrame,
    table: str,
    *,
    dedupe_keys: list[str] | None = None,
) -> None:
    """Overwrite a Delta table after deduping bootstrap rows by natural key."""
    frame = dedupe_pandas(pdf, dedupe_keys) if dedupe_keys else pdf
    spark_df = pandas_to_spark(spark, frame)
    if dedupe_keys:
        available = [key for key in dedupe_keys if key in frame.columns]
        if available:
            spark_df = spark_df.dropDuplicates(available)
    (
        spark_df.write.format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(table)
    )


def append_delta_table(spark, pdf: pd.DataFrame, table: str) -> None:
    """Append rows to a Delta table, creating it when missing."""
    if pdf.empty:
        return
    spark_df = pandas_to_spark(spark, pdf)
    (
        spark_df.write.format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable(table)
    )


def conflicting_column_names(
    left_types: dict[str, str],
    right_types: dict[str, str],
) -> set[str]:
    """Return shared columns whose Spark simple types differ."""
    return {
        name
        for name in set(left_types) & set(right_types)
        if left_types[name] != right_types[name]
    }


def _spark_type_map(df) -> dict[str, str]:
    return {field.name: field.dataType.simpleString() for field in df.schema.fields}


def harmonize_pair_for_union(left, right):
    """Cast conflicting shared columns to string before unionByName."""
    from pyspark.sql import functions as F

    left_types = _spark_type_map(left)
    right_types = _spark_type_map(right)
    for column in sorted(conflicting_column_names(left_types, right_types)):
        left = left.withColumn(column, F.col(column).cast("string"))
        right = right.withColumn(column, F.col(column).cast("string"))
    return left, right


def union_by_name_harmonized(frames):
    """Union Spark DataFrames, harmonizing cross-season schema drift as strings."""
    if not frames:
        raise ValueError("At least one DataFrame is required")

    result = frames[0]
    for frame in frames[1:]:
        result, frame = harmonize_pair_for_union(result, frame)
        result = result.unionByName(frame, allowMissingColumns=True)
    return result