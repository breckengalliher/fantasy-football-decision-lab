from pathlib import Path

import pandas as pd
import pytest

from src.projection_ledger import append_forecast_snapshot, build_forecast_snapshot, frame_fingerprint


def sample_board() -> pd.DataFrame:
    return pd.DataFrame([{
        "player_id": "p1", "player": "Player One", "team": "SEA", "position": "WR",
        "next_opponent": "SF", "is_roster_relevant": True, "projected_ppr": 14.2,
        "median_ppr": 14.2, "floor_ppr": 8.1, "ceiling_ppr": 21.3,
        "games_played": 4, "season_ppr": 13.0, "recent_ppr": 15.0,
        "recent_opportunities": 8.0, "injury_status_live": None,
    }])


def test_ledger_snapshot_has_point_in_time_fields(tmp_path: Path):
    snapshot = build_forecast_snapshot(
        sample_board(), season=2026, week=5, scoring_format="PPR-4PT-PASS-TD",
        model_version="round-three", forecast_timestamp="2026-10-08T12:00:00+00:00",
        information_cutoff="2026-10-08T11:55:00+00:00", snapshot_id="fixed",
    )
    path = append_forecast_snapshot(snapshot, tmp_path)
    stored = pd.read_parquet(path)
    assert stored.loc[0, "information_cutoff"] == "2026-10-08T11:55:00+00:00"
    assert stored.loc[0, "availability_scenario"] == "baseline"
    assert stored.loc[0, "model_version"] == "round-three"


def test_ledger_refuses_to_overwrite_snapshot(tmp_path: Path):
    snapshot = build_forecast_snapshot(
        sample_board(), season=2026, week=5, scoring_format="PPR-4PT-PASS-TD",
        model_version="round-three", forecast_timestamp="2026-10-08T12:00:00+00:00",
        snapshot_id="fixed",
    )
    append_forecast_snapshot(snapshot, tmp_path)
    with pytest.raises(FileExistsError):
        append_forecast_snapshot(snapshot, tmp_path)


def test_fingerprint_changes_when_projection_input_changes():
    first = sample_board()
    second = first.copy()
    second.loc[0, "recent_opportunities"] = 9.0
    assert frame_fingerprint(first) != frame_fingerprint(second)
