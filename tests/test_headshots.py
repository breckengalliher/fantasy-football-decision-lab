import pandas as pd

from dashboard.headshots import HeadshotContext, enrich_with_headshots, normalize_headshots


def test_normalize_headshots_keeps_supported_active_roster_players():
    records = normalize_headshots({
        "6786": {"player_id": "6786", "full_name": "CeeDee Lamb", "team": "DAL", "position": "WR", "active": True},
        "coach": {"player_id": "coach", "full_name": "A Coach", "team": "DAL", "position": "HC", "active": True},
        "retired": {"player_id": "retired", "full_name": "Old Player", "team": None, "position": "WR", "active": False},
    })

    assert records[["player_key", "team", "position"]].to_dict("records") == [
        {"player_key": "ceedee lamb", "team": "DAL", "position": "WR"}
    ]
    assert records.loc[0, "headshot_url"].endswith("/6786.jpg")


def test_enrich_headshots_requires_name_team_and_position_match():
    records = normalize_headshots({
        "6786": {"player_id": "6786", "full_name": "CeeDee Lamb", "team": "DAL", "position": "WR", "active": True}
    })
    context = HeadshotContext(records, "2026-10-07T00:00:00+00:00", "Connected")
    board = pd.DataFrame([
        {"player": "CeeDee Lamb", "team": "DAL", "position": "WR"},
        {"player": "CeeDee Lamb", "team": "SEA", "position": "WR"},
    ])

    result = enrich_with_headshots(board, context)

    assert pd.notna(result.loc[0, "headshot_url"])
    assert pd.isna(result.loc[1, "headshot_url"])


def test_headshots_normalize_nflverse_rams_team_alias():
    records = normalize_headshots({
        "1": {"player_id": "1", "full_name": "Rams Player", "team": "LAR", "position": "WR", "active": True}
    })
    assert records.loc[0, "team"] == "LA"
