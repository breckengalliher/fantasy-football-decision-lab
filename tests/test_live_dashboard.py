from datetime import date

import pandas as pd

from dashboard.data import build_start_sit_board, current_nfl_season


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
