import pandas as pd

from src.start_sit_backtest import (
    add_prediction,
    add_shrunk_prediction,
    build_backtest_rows,
    calibrate,
    clustered_mae_difference_ci,
    pairwise_ordering_accuracy,
)


def test_backtest_uses_only_prior_games():
    rows = []
    for week, points in enumerate([10, 20, 30, 40], start=1):
        rows.append({"season": 2025, "week": week, "player_id": "p1", "position": "WR", "opponent_team": "OPP", "fantasy_points_ppr": points, "targets": 6})
        rows.append({"season": 2025, "week": week, "player_id": f"other{week}", "position": "WR", "opponent_team": "OPP", "fantasy_points_ppr": 10, "targets": 6})
    result = build_backtest_rows(pd.DataFrame(rows), min_prior_games=3)
    player = result.loc[result["player_id"].eq("p1")].iloc[0]
    assert player["week"] == 4
    assert player["season_ppr"] == 20
    assert player["recent_ppr"] == 20
    assert player["target_ppr"] == 40


def test_calibration_returns_position_intervals():
    rows = pd.DataFrame({
        "position": ["WR"] * 5,
        "recent_ppr": [10, 11, 12, 13, 14],
        "season_ppr": [10] * 5,
        "matchup_index": [1] * 5,
        "target_ppr": [8, 10, 12, 14, 16],
    })
    grid, best, intervals = calibrate(rows)
    assert len(grid) == 84
    assert 0 <= best["recent_weight"] <= 1
    assert intervals.loc[0, "floor_offset"] <= intervals.loc[0, "ceiling_offset"]


def test_pairwise_accuracy_and_clustered_interval():
    rows = pd.DataFrame({
        "season": [2024] * 4,
        "week": [1, 1, 2, 2],
        "position": ["WR"] * 4,
        "recent_ppr": [20, 10, 18, 8],
        "season_ppr": [20, 10, 18, 8],
        "matchup_index": [1.0] * 4,
        "target_ppr": [21, 9, 19, 7],
    })
    predicted = add_prediction(rows, .1, .25)
    assert pairwise_ordering_accuracy(predicted) == 1.0
    point, low, high = clustered_mae_difference_ci(rows, (.1, .25), (.65, .25), samples=20)
    assert low <= point <= high


def test_balanced_shrinkage_uses_more_current_data_over_time():
    rows = pd.DataFrame({
        "games_played": [4, 8, 12], "recent_ppr": [30] * 3, "season_ppr": [30] * 3,
        "history_anchor": [10] * 3, "matchup_index": [1] * 3, "target_ppr": [20] * 3,
    })
    result = add_shrunk_prediction(rows, "balanced")
    assert result["current_season_weight"].tolist() == [.4, .75, .9]
    assert result["prediction"].is_monotonic_increasing
