from datetime import date

import pandas as pd

from dashboard.data import (
    SCORING_ROLE_TD_EXCEPTION_ENABLED,
    SCORING_ROLE_TD_EXCEPTION_REQUIREMENT,
    apply_qb_scoring_mode,
    apply_verified_starter_gate,
    build_start_sit_board,
    current_nfl_season,
)


def test_scoring_role_td_exception_remains_policy_locked():
    assert SCORING_ROLE_TD_EXCEPTION_ENABLED is False
    assert SCORING_ROLE_TD_EXCEPTION_REQUIREMENT == "verified red-zone or goal-line opportunity data"


def test_current_nfl_season_changes_in_september():
    assert current_nfl_season(date(2026, 8, 31)) == 2025
    assert current_nfl_season(date(2026, 9, 1)) == 2026


def test_matchup_adjustment_rewards_easier_opponent():
    rows = []
    for week in range(1, 5):
        rows.extend([
            {"season": 2026, "week": week, "season_type": "REG", "player_id": "a", "player_display_name": "Alpha", "position": "WR", "recent_team": "AAA", "opponent_team": "CCC", "fantasy_points_ppr": 12},
            {"season": 2026, "week": week, "season_type": "REG", "player_id": "b", "player_display_name": "Bravo", "position": "WR", "recent_team": "BBB", "opponent_team": "DDD", "fantasy_points_ppr": 12},
            {"season": 2026, "week": week, "season_type": "REG", "player_id": f"c{week}", "player_display_name": f"C{week}", "position": "WR", "recent_team": "EEE", "opponent_team": "CCC", "fantasy_points_ppr": 20},
            {"season": 2026, "week": week, "season_type": "REG", "player_id": f"d{week}", "player_display_name": f"D{week}", "position": "WR", "recent_team": "FFF", "opponent_team": "DDD", "fantasy_points_ppr": 5},
        ])
    schedules = pd.DataFrame([{"season": 2026, "week": 5, "game_type": "REG", "home_team": "AAA", "away_team": "CCC"}, {"season": 2026, "week": 5, "game_type": "REG", "home_team": "BBB", "away_team": "DDD"}])
    board, week = build_start_sit_board(pd.DataFrame(rows), schedules, 2026)
    alpha = board.loc[board["player"].eq("Alpha")].iloc[0]
    bravo = board.loc[board["player"].eq("Bravo")].iloc[0]
    assert week == 5
    assert alpha["projected_ppr"] > bravo["projected_ppr"]


def test_verified_starter_gate_requires_live_qb1():
    board = pd.DataFrame([
        {"player": "Starter", "position": "QB", "depth_position_live": "QB", "depth_order_live": 1},
        {"player": "Backup", "position": "QB", "depth_position_live": "QB", "depth_order_live": 2},
        {"player": "Receiver", "position": "WR", "depth_position_live": "WR", "depth_order_live": 2},
    ])
    result = apply_verified_starter_gate(board).set_index("player")
    assert bool(result.loc["Starter", "verified_qb_starter"])
    assert not bool(result.loc["Backup", "verified_qb_starter"])
    assert bool(result.loc["Receiver", "verified_qb_starter"])


def test_qb_scoring_toggle_changes_qbs_only():
    board = pd.DataFrame([
        {
            "player_id": "qb", "player": "Quarterback", "position": "QB", "next_opponent": "BBB",
            "season_ppr": 20.0, "recent_ppr": 20.0, "points_allowed": 20.0, "matchup_index": 1.0,
            "projected_ppr": 20.0, "median_ppr": 20.0, "floor_ppr": 10.0, "ceiling_ppr": 30.0,
        },
        {
            "player_id": "wr", "player": "Receiver", "position": "WR", "next_opponent": "BBB",
            "season_ppr": 10.0, "recent_ppr": 10.0, "points_allowed": 10.0, "matchup_index": 1.0,
            "projected_ppr": 10.0, "median_ppr": 10.0, "floor_ppr": 5.0, "ceiling_ppr": 15.0,
        },
    ])
    weekly = pd.DataFrame([
        {"player_id": "qb", "position": "QB", "week": 1, "opponent_team": "BBB", "fantasy_points_ppr": 20.0, "passing_tds": 2, "carries": 4, "rushing_yards": 20},
        {"player_id": "qb", "position": "QB", "week": 2, "opponent_team": "BBB", "fantasy_points_ppr": 20.0, "passing_tds": 2, "carries": 4, "rushing_yards": 20},
        {"player_id": "wr", "position": "WR", "week": 1, "opponent_team": "BBB", "fantasy_points_ppr": 10.0, "passing_tds": 0, "carries": 0, "rushing_yards": 0},
    ])
    four = apply_qb_scoring_mode(board, weekly, 4).set_index("player")
    six = apply_qb_scoring_mode(board, weekly, 6).set_index("player")
    assert six.loc["Quarterback", "median_ppr"] > four.loc["Quarterback", "median_ppr"]
    assert six.loc["Receiver", "median_ppr"] == four.loc["Receiver", "median_ppr"]
