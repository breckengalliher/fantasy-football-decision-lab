from pathlib import Path

import pandas as pd
import pytest

from src.context_ledger import append_context_snapshot, build_context_snapshot


def test_context_snapshot_preserves_observed_fields_and_missing_sources(tmp_path: Path):
    board = pd.DataFrame([{
        "player_id": "p1", "player": "Player", "team": "SEA", "position": "WR",
        "next_opponent": "SF", "is_roster_relevant": True,
        "injury_status_live": "Questionable", "depth_order_live": 2,
        "latest_snap_pct": .72,
    }])
    snapshot = build_context_snapshot(
        board, season=2026, week=5, captured_at="2026-10-08T18:00:00+00:00"
    )
    assert snapshot.loc[0, "injury_status_live"] == "Questionable"
    assert snapshot.loc[0, "routes_available"] == False
    assert snapshot.loc[0, "first_read_share_available"] == False
    assert append_context_snapshot(snapshot, tmp_path).exists()


def test_context_ledger_is_append_only(tmp_path: Path):
    snapshot = build_context_snapshot(
        pd.DataFrame([{"player_id": "p1", "is_roster_relevant": True}]),
        season=2026, week=5, captured_at="2026-10-08T18:00:00+00:00",
    )
    append_context_snapshot(snapshot, tmp_path)
    with pytest.raises(FileExistsError):
        append_context_snapshot(snapshot, tmp_path)
