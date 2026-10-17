import pandas as pd

from nfl_predictions.core import build_player_dimension, extract_pbp_player_roles


def test_build_player_dimension_dedupes_and_labels_collisions():
    rosters = pd.DataFrame(
        {
            "gsis_id": ["P1", "P2", "P3"],
            "full_name": ["John Smith", "John Smith", "Jane Doe"],
            "team": ["NYG", "DAL", "SEA"],
            "position": ["QB", "WR", "RB"],
            "season": [2026, 2026, 2026],
            "week": [1, 1, 1],
        }
    )

    players = build_player_dimension(rosters)
    assert len(players) == 3
    assert players["player_id"].tolist() == ["P1", "P2", "P3"]
    assert players.loc[players["gsis_id"] == "P1", "player_label"].iloc[0] == "John Smith (NYG)"
    assert players.loc[players["gsis_id"] == "P2", "player_label"].iloc[0] == "John Smith (DAL)"
    assert players.loc[players["gsis_id"] == "P3", "player_label"].iloc[0] == "Jane Doe"
    assert int(players["name_collision"].sum()) == 2


def test_extract_pbp_player_roles_long_format():
    pbp = pd.DataFrame(
        {
            "game_id": ["g1", "g1"],
            "play_id": [1, 2],
            "season": [2025, 2025],
            "season_type": ["REG", "REG"],
            "week": [1, 1],
            "game_type": ["REG", "REG"],
            "passer_player_id": ["P1", None],
            "passer_player_name": ["Passer", None],
            "rusher_player_id": [None, "P2"],
            "rusher_player_name": [None, "Rusher"],
        }
    )

    roles = extract_pbp_player_roles(pbp)
    assert len(roles) == 2
    assert set(roles["role"]) == {"passer", "rusher"}
    assert set(roles["player_id"]) == {"P1", "P2"}