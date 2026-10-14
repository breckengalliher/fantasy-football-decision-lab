import hashlib
import json
import sys
from types import SimpleNamespace
import pandas as pd
import pytest
import src.refresh_live_context as refresh
from dashboard.providers.injuries import InjuryContext
from dashboard.providers.sportsdataio import SportsDataIOContext

@pytest.fixture
def staged_case(tmp_path, monkeypatch):
    metadata = {"season": 2026, "next_week": 5, "refreshed_qb_passing_td_formats": [4, 6],
                "refreshed_at": "2026-10-09T12:00:00Z"}
    (tmp_path/"live_refresh_metadata.json").write_text(json.dumps(metadata))
    (tmp_path/"publication_manifest.json").write_text('{"version":"last-good"}')
    for points in (4, 6):
        pd.DataFrame([dict(player_id="p1", player="Fixture", team="SEA", position="QB",
            is_roster_relevant=True, floor_ppr=8., median_ppr=14.+points, ceiling_ppr=26.,
            projected_ppr=14.+points, next_opponent="SF", recent_opportunities=8.)]).to_parquet(
                tmp_path/f"live_start_sit_board_{points}pt_current.parquet", index=False)
    pd.DataFrame([dict(player_id="p1", week=1, ppr=14.)]).to_parquet(tmp_path/"live_weekly_current.parquet")
    provider = SportsDataIOContext(pd.DataFrame(),pd.DataFrame([dict(team="SEA", provider_opponent="SF",
        spread_line_live=-3.5)]),pd.DataFrame(),"2026-10-11T12:01:00Z")
    injury = InjuryContext(pd.DataFrame([dict(player_key="fixture",team="SEA",injury_status_live="Unknown")]),
        provider.refreshed_at,"Connected · 1 Week 5 record","Not requested")
    monkeypatch.setattr(refresh,"PROCESSED",tmp_path)
    monkeypatch.setattr(refresh,"CONTEXT_LEDGER",tmp_path/"ledger")
    monkeypatch.setattr(refresh,"api_key",lambda:"fixture-only-key")
    monkeypatch.setattr(refresh,"SportsDataIOClient",lambda key:SimpleNamespace(weekly_context=lambda *a:provider))
    monkeypatch.setattr(refresh,"load_daily_injury_context",lambda *a:injury)
    monkeypatch.setattr(refresh,"build_personnel_context",lambda *a:(pd.DataFrame(),pd.DataFrame()))
    monkeypatch.setattr(refresh,"append_context_snapshot",lambda *a:None)
    monkeypatch.setattr(sys,"argv",["refresh_live_context.py"])
    return tmp_path

def fingerprints(path):
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir() if p.is_file()}

def test_failed_second_format_validation_keeps_every_last_good_output(staged_case,monkeypatch):
    before=fingerprints(staged_case)
    actual=refresh.refresh_board
    def broken(*a,**kw):
        frame=actual(*a,**kw)
        if kw["passing_td_points"]==6:
            frame["spread_line_live_x"]=-9.
        return frame
    monkeypatch.setattr(refresh,"refresh_board",broken)
    with pytest.raises(ValueError,match="merge artifacts"):
        refresh.main()
    assert fingerprints(staged_case)==before
    assert not list(staged_case.glob(".context-stage-*"))

def test_success_validates_both_formats_and_does_not_publish_pointer(staged_case):
    before=(staged_case/"publication_manifest.json").read_bytes()
    refresh.main()
    metadata=json.loads((staged_case/"live_refresh_metadata.json").read_text())
    assert metadata["context_refreshed_at"] != metadata["refreshed_at"]
    assert metadata["injury_freshness_verified"] is False
    for points in (4,6):
        board=pd.read_parquet(staged_case/f"live_start_sit_board_{points}pt_current.parquet")
        assert board.iloc[0].median_ppr==14.+points
        assert board.iloc[0].spread_line_live==-3.5
        assert board.columns.is_unique
    assert (staged_case/"sportsdataio_games_current.parquet").is_file()
    assert (staged_case/"general_injury_context_current.parquet").is_file()
    assert (staged_case/"publication_manifest.json").read_bytes()==before

