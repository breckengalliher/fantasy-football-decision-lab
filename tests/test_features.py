import pandas as pd

from src.features import add_early_season_fallback_features, add_previous_game_features


def test_rolling_window_excludes_current_game() -> None:
    data = pd.DataFrame(
        {
            "player_id": ["A"] * 6,
            "season": [2024] * 6,
            "week": [1, 2, 3, 4, 5, 6],
            "target_share": [0.10, 0.20, 0.30, 0.40, 0.50, 0.90],
            "air_yards_share": [0.15, 0.25, 0.35, 0.45, 0.55, 0.95],
            "fantasy_points_ppr": [5, 10, 15, 20, 25, 100],
        }
    )
    result = add_previous_game_features(data)

    assert result.loc[5, "rolling_5_target_share"] == 0.30
    assert result.loc[5, "rolling_5_air_yards_share"] == 0.35
    assert result.loc[5, "rolling_5_fantasy_points_ppr"] == 15


def test_zero_target_game_is_included() -> None:
    data = pd.DataFrame(
        {
            "player_id": ["A"] * 4,
            "season": [2024] * 4,
            "week": [1, 2, 3, 4],
            "target_share": [0.30, 0.00, 0.30, 0.60],
            "air_yards_share": [0.30, 0.00, 0.30, 0.60],
            "fantasy_points_ppr": [12, 0, 12, 24],
        }
    )
    result = add_previous_game_features(data, windows=(3,))

    assert result.loc[3, "rolling_3_target_share"] == 0.20
    assert result.loc[3, "rolling_3_air_yards_share"] == 0.20


def test_history_restarts_each_season() -> None:
    data = pd.DataFrame(
        {
            "player_id": ["A", "A"],
            "season": [2023, 2024],
            "week": [18, 1],
            "target_share": [0.50, 0.20],
            "air_yards_share": [0.60, 0.30],
            "fantasy_points_ppr": [30, 10],
        }
    )
    result = add_previous_game_features(data)

    assert pd.isna(result.loc[1, "previous_game_target_share"])


def test_fallback_history_crosses_season() -> None:
    data = pd.DataFrame(
        {
            "player_id": ["A"] * 6,
            "season": [2023, 2023, 2023, 2023, 2023, 2024],
            "week": [14, 15, 16, 17, 18, 1],
            "team": ["AAA"] * 6,
            "target_share": [0.10, 0.20, 0.30, 0.40, 0.50, 0.60],
            "air_yards_share": [0.15, 0.25, 0.35, 0.45, 0.55, 0.65],
            "fantasy_points_ppr": [5, 10, 15, 20, 25, 30],
        }
    )
    result = add_early_season_fallback_features(data)

    assert result.loc[5, "fallback_rolling_5_target_share"] == 0.30
    assert result.loc[5, "fallback_history_crosses_offseason"]
    assert result.loc[5, "dashboard_confidence"] == "reduced"


def test_team_change_receives_low_confidence() -> None:
    data = pd.DataFrame(
        {
            "player_id": ["A"] * 6,
            "season": [2023, 2023, 2023, 2023, 2023, 2024],
            "week": [14, 15, 16, 17, 18, 1],
            "team": ["AAA", "AAA", "AAA", "AAA", "AAA", "BBB"],
            "target_share": [0.10, 0.20, 0.30, 0.40, 0.50, 0.60],
            "air_yards_share": [0.15, 0.25, 0.35, 0.45, 0.55, 0.65],
            "fantasy_points_ppr": [5, 10, 15, 20, 25, 30],
        }
    )
    result = add_early_season_fallback_features(data)

    assert result.loc[5, "changed_team_since_previous_appearance"]
    assert result.loc[5, "dashboard_confidence"] == "low"
