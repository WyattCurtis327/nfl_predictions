from nfl_predictions.teams import is_known_team, to_abbr, unmapped_team_names


def test_to_abbr_maps_full_names():
    assert to_abbr("Kansas City Chiefs") == "KC"
    assert to_abbr("San Francisco 49ers") == "SF"


def test_to_abbr_returns_none_for_unknown_team():
    assert to_abbr("London Monarchs") is None


def test_unmapped_team_names_dedupes_and_sorts():
    names = unmapped_team_names(
        ["Kansas City Chiefs", "London Monarchs", "Paris Musketeers", "London Monarchs"]
    )
    assert names == ["London Monarchs", "Paris Musketeers"]
    assert is_known_team("Kansas City Chiefs")
    assert not is_known_team("London Monarchs")