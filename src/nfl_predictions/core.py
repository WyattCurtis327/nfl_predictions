"""Build collision-safe player dimensions keyed by official IDs."""

from __future__ import annotations

import pandas as pd

PLAYER_KEY = "gsis_id"
GAME_KEY = "game_id"

PLAYER_DIM_COLUMNS = [
    "player_id",
    "gsis_id",
    "full_name",
    "player_label",
    "name_collision",
    "team",
    "position",
    "jersey_number",
    "status",
    "espn_id",
    "season",
    "week",
]

PLAYER_ROLE_COLUMNS = [
    "game_id",
    "play_id",
    "season",
    "season_type",
    "week",
    "game_type",
    "player_id",
    "player_name",
    "role",
]


def build_player_dimension(rosters: pd.DataFrame) -> pd.DataFrame:
    """One row per player, keyed by gsis_id — never by name alone."""
    if rosters.empty:
        return pd.DataFrame(columns=PLAYER_DIM_COLUMNS)

    df = rosters.dropna(subset=[PLAYER_KEY]).copy()
    df["player_id"] = df[PLAYER_KEY]
    name_counts = df.groupby("full_name", dropna=False)[PLAYER_KEY].transform("count")
    df["name_collision"] = name_counts > 1
    df["player_label"] = df.apply(
        lambda row: f"{row['full_name']} ({row['team']})"
        if row["name_collision"]
        else row["full_name"],
        axis=1,
    )

    sort_cols = [c for c in ["player_id", "week", "season"] if c in df.columns]
    df = df.sort_values(sort_cols).drop_duplicates(subset=["player_id"], keep="last")

    available = [c for c in PLAYER_DIM_COLUMNS if c in df.columns]
    return df[available].reset_index(drop=True)


def extract_pbp_player_roles(pbp: pd.DataFrame) -> pd.DataFrame:
    """Long-format player role references using gsis player_id, not names."""
    role_specs = [
        ("passer", "passer_player_id", "passer_player_name"),
        ("rusher", "rusher_player_id", "rusher_player_name"),
        ("receiver", "receiver_player_id", "receiver_player_name"),
        ("kicker", "kicker_player_id", "kicker_player_name"),
        ("punter", "punter_player_id", "punter_player_name"),
        ("fantasy", "fantasy_player_id", "fantasy_player_name"),
    ]

    base_cols = [
        c
        for c in ["game_id", "play_id", "season", "season_type", "week", "game_type"]
        if c in pbp.columns
    ]
    frames: list[pd.DataFrame] = []

    for role, id_col, name_col in role_specs:
        if id_col not in pbp.columns:
            continue
        subset = pbp[base_cols + [id_col, name_col]].copy()
        subset = subset.dropna(subset=[id_col])
        subset = subset.rename(columns={id_col: "player_id", name_col: "player_name"})
        subset["role"] = role
        frames.append(subset)

    if not frames:
        return pd.DataFrame(columns=PLAYER_ROLE_COLUMNS)

    roles = pd.concat(frames, ignore_index=True)
    roles["player_id"] = roles["player_id"].astype(str)
    return roles.drop_duplicates().reset_index(drop=True)