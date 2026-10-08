import pandas as pd

from src.model_validation_audit import historical_data_audit, metric_summary


def test_data_audit_labels_missing_point_in_time_features():
    frame = pd.DataFrame([{
        "season": 2025, "week": 1, "player_id": "p1", "position": "WR",
        "opponent_team": "SF", "fantasy_points_ppr": 12.0, "season_type": "REG",
        "attempts": 0, "carries": 0, "targets": 8,
    }])
    audit = historical_data_audit(frame)
    assert audit["feature_availability"]["box_score_opportunity"]["complete"] is True
    assert audit["feature_availability"]["historical_injury_timestamp"]["complete"] is False
    assert "not an archive" in audit["point_in_time_classification"]


def test_metric_summary_reports_bias_as_actual_minus_projection():
    rows = pd.DataFrame({"target_ppr": [10.0, 20.0], "model": [8.0, 22.0]})
    result = metric_summary(rows, "model")
    assert result["samples"] == 2
    assert result["mae"] == 2.0
    assert result["bias_actual_minus_projection"] == 0.0
