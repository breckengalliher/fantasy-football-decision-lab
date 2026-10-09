from __future__ import annotations

import pandas as pd

from dashboard.sleeper_client import map_player_records, map_players, passing_td_points, roster_shape


def test_roster_shape_maps_flex_and_reports_unsupported_slots():
    counts, ignored = roster_shape(("QB", "RB", "RB", "WR", "TE", "W/R/T", "SUPER_FLEX", "BN", "K", "DEF"))
    assert counts["QB"] == 1
    assert counts["RB"] == 2
    assert counts["FLEX"] == 1
    assert counts["SUPERFLEX"] == 1
    assert counts["BENCH"] == 1
    assert ignored == ["K", "DEF"]


def test_passing_td_points_preserves_supported_formats_and_flags_other_values():
    assert passing_td_points({"pass_td": 6}) == (6, None)
    points, warning = passing_td_points({"pass_td": 5})
    assert points == 4
    assert "5-point" in warning


def test_player_mapping_prefers_gsis_and_uses_unambiguous_name_fallback():
    board = pd.DataFrame([
        {"player_id": "00-1", "player": "Alpha Runner", "position": "RB", "team": "SEA"},
        {"player_id": "00-2", "player": "Bravo Receiver", "position": "WR", "team": "DAL"},
    ])
    sleeper = {
        "10": {"gsis_id": "00-1", "full_name": "Different Name", "position": "RB"},
        "11": {"full_name": "Bravo Receiver", "position": "WR"},
        "12": {"full_name": "Unknown Player", "position": "TE"},
    }
    mapped, unmatched = map_players(["10", "11", "12"], sleeper, board)
    assert mapped == ["00-1", "00-2"]
    assert unmatched == ["Unknown Player"]


def test_duplicate_name_is_not_guessed_and_external_id_is_preserved():
    board = pd.DataFrame([
        {"player_id": "00-1", "player": "Same Name", "position": "WR", "team": "SEA"},
        {"player_id": "00-2", "player": "Same Name", "position": "WR", "team": "DAL"},
    ])
    sleeper = {"55": {"full_name": "Same Name", "position": "WR", "team": "SEA"}}
    records = map_player_records(["55"], sleeper, board)
    assert records == [{"external_player_id": "55", "player_id": None, "name": "Same Name", "position": "WR", "team": "SEA", "match_method": None, "matched": False}]
