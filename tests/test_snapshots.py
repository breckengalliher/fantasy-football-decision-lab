import pandas as pd

from dashboard.snapshots import build_personnel_context


def test_personnel_context_detects_qb_and_line_changes():
    previous = pd.DataFrame([
        {"player_key": "old qb", "team": "AAA", "depth_position_live": "QB", "depth_order_live": 1},
        {"player_key": "old lt", "team": "AAA", "depth_position_live": "LT", "depth_order_live": 1},
    ])
    current = pd.DataFrame([
        {"player_key": "new qb", "team": "AAA", "depth_position_live": "QB", "depth_order_live": 1},
        {"player_key": "new lt", "team": "AAA", "depth_position_live": "LT", "depth_order_live": 1},
    ])
    _, teams = build_personnel_context(current, previous)
    assert bool(teams.loc[0, "qb_changed"])
    assert bool(teams.loc[0, "ol_changed"])
