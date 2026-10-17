import pandas as pd

from nfl_predictions.spark_io import (
    conflicting_column_names,
    dedupe_pandas,
    prepare_pandas_for_spark,
)


def test_conflicting_column_names_detects_type_mismatch():
    left = {"passer_player_id": "bigint", "week": "int", "game_id": "string"}
    right = {"passer_player_id": "string", "week": "int", "game_id": "string"}
    assert conflicting_column_names(left, right) == {"passer_player_id"}


def test_conflicting_column_names_ignores_missing_columns():
    left = {"week": "int"}
    right = {"week": "int", "season": "int"}
    assert conflicting_column_names(left, right) == set()


def test_prepare_pandas_for_spark_preserves_nullable_booleans():
    frame = pd.DataFrame(
        {
            "spread_correct": [True, False, None],
            "spread_push": [False, None, True],
            "note": ["a", "b", "c"],
        }
    )
    prepared = prepare_pandas_for_spark(frame)
    assert str(prepared["spread_correct"].dtype) == "boolean"
    assert str(prepared["spread_push"].dtype) == "boolean"
    assert str(prepared["note"].dtype) == "string"


def test_dedupe_pandas_keeps_latest_row_per_key():
    frame = pd.DataFrame(
        {
            "game_id": ["g1", "g1", "g2"],
            "spread_line": [-3.5, -4.0, -1.0],
        }
    )

    result = dedupe_pandas(frame, ["game_id"])

    assert len(result) == 2
    assert result.loc[result["game_id"] == "g1", "spread_line"].iloc[0] == -4.0