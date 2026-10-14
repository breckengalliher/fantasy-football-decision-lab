from datetime import datetime, timezone

import pandas as pd

from src.audit_injury_practice_coverage import coverage_observation


def test_coverage_observation_matches_relevant_players_without_assuming_health():
    eligible = pd.DataFrame([
        {"player_key": "alpha", "team": "SEA"},
        {"player_key": "bravo", "team": "DAL"},
        {"player_key": "charlie", "team": "HOU"},
    ])
    injuries = pd.DataFrame([
        {"player_key": "alpha", "team": "SEA", "injury_status_live": "Questionable", "practice_status_live": "Limited", "injury_updated_live": "2026-10-07"},
        {"player_key": "bravo", "team": "DAL", "injury_status_live": "Doubtful", "practice_status_live": pd.NA, "injury_updated_live": "2026-10-07"},
        {"player_key": "reserve", "team": "NYJ", "injury_status_live": "Out", "practice_status_live": "DNP", "injury_updated_live": "2026-10-07"},
    ])

    result = coverage_observation(
        eligible,
        injuries,
        "2026-10-07T22:00:00+00:00",
        datetime(2026, 10, 7, 22, 5, tzinfo=timezone.utc),
    )

    assert result["eligible_players"] == 3
    assert result["matched_relevant_records"] == 2
    assert result["unmatched_provider_records"] == 1
    assert result["status_completeness"] == 1.0
    assert result["practice_completeness"] == 0.5
    assert "charlie" not in result  # no provider record is not converted to healthy
