import json
from datetime import datetime,timezone
import pytest
from src.qa_provider_publication import stage_context

def test_both_formats_keep_points_and_source_time(tmp_path,monkeypatch):
    import pandas as pd
    monkeypatch.setenv('SDL_QA_PROVIDER_PUBLICATION','1')
    monkeypatch.setenv('GITHUB_REPOSITORY','breckengalliher/sdl-release-qa-scheduler')
    source=tmp_path/'source'; source.mkdir()
    metadata={'season':2026,'next_week':6,'refreshed_qb_passing_td_formats':[4,6],
              'refreshed_at':'2026-10-13T12:00:00Z','injury_freshness_verified':False,'depth_freshness_verified':False}
    (source/'live_refresh_metadata.json').write_text(json.dumps(metadata))
    for points in (4,6):
        pd.DataFrame([{'player_id':'test','player':'Example','team':'SEA','position':'QB',
                       'floor_ppr':1.,'median_ppr':float(points),'ceiling_ppr':20.,'projected_ppr':float(points),
                       'is_roster_relevant':True}]).to_parquet(source/f'live_start_sit_board_{points}pt_current.parquet',index=False)
    pd.DataFrame([{'player_id':'test','week':5}]).to_parquet(source/'live_weekly_current.parquet',index=False)
    at=datetime.now(timezone.utc).isoformat()
    observation={'season':2026,'week':6,'official_freshness_verified':False,'source_retrieved_at':at,'validated_at':at}
    result=stage_context(source,tmp_path/'out',observation)
    assert result['metadata']['refreshed_at']==metadata['refreshed_at']
    for points in (4,6):
        board=pd.read_parquet(tmp_path/'out'/f'live_start_sit_board_{points}pt_current.parquet')
        assert board.median_ppr.iloc[0]==points
        assert json.loads(board.qa_provider_context_json.iloc[0])['recommendation_allowed'] is False

def test_week_mismatch_preserves_existing_snapshot(tmp_path,monkeypatch):
    monkeypatch.setenv('SDL_QA_PROVIDER_PUBLICATION','1')
    monkeypatch.setenv('GITHUB_REPOSITORY','breckengalliher/sdl-release-qa-scheduler')
    source=tmp_path/'source'; source.mkdir()
    metadata={'season':2026,'next_week':5,'refreshed_at':'original'}
    (source/'live_refresh_metadata.json').write_text(json.dumps(metadata))
    destination=tmp_path/'stage'
    with pytest.raises(ValueError,match='season/week mismatch'):
        stage_context(source,destination,{'season':2026,'week':6})
    assert not destination.exists()
    assert json.loads((source/'live_refresh_metadata.json').read_text())==metadata

def test_unapproved_repository_cannot_stage(tmp_path,monkeypatch):
    monkeypatch.setenv('SDL_QA_PROVIDER_PUBLICATION','1')
    monkeypatch.setenv('GITHUB_REPOSITORY','production')
    with pytest.raises(ValueError,match='disabled'):
        stage_context(tmp_path/'source',tmp_path/'out',{})

def test_official_claim_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv('SDL_QA_PROVIDER_PUBLICATION','1')
    monkeypatch.setenv('GITHUB_REPOSITORY','breckengalliher/sdl-release-qa-scheduler')
    source=tmp_path/'source'; source.mkdir()
    (source/'live_refresh_metadata.json').write_text(json.dumps({'season':2026,'next_week':6}))
    with pytest.raises(ValueError,match='official availability'):
        stage_context(source,tmp_path/'out',{'season':2026,'week':6,'official_freshness_verified':True})
