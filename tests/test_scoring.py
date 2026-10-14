import pandas as pd

from src.scoring import add_basic_receiving_metrics, calculate_receiving_ppr_points


def test_receiving_ppr_points() -> None:
    points = calculate_receiving_ppr_points(
        pd.Series([7]), pd.Series([100]), pd.Series([1])
    )
    assert points.iloc[0] == 23.0


def test_zero_targets_produce_missing_rates() -> None:
    data = pd.DataFrame(
        {
            "receptions": [0],
            "receiving_yards": [0],
            "receiving_tds": [0],
            "targets": [0],
            "receiving_air_yards": [0],
        }
    )
    result = add_basic_receiving_metrics(data)
    assert pd.isna(result.loc[0, "catch_rate"])
    assert pd.isna(result.loc[0, "average_depth_of_target"])


def test_basic_metrics() -> None:
    data = pd.DataFrame(
        {
            "receptions": [5],
            "receiving_yards": [80],
            "receiving_tds": [1],
            "targets": [10],
            "receiving_air_yards": [120],
        }
    )
    result = add_basic_receiving_metrics(data)
    assert result.loc[0, "ppr_receiving_points"] == 19.0
    assert result.loc[0, "catch_rate"] == 0.5
    assert result.loc[0, "yards_per_target"] == 8.0
    assert result.loc[0, "average_depth_of_target"] == 12.0
