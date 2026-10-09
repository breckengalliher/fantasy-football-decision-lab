"""Permanent repair regressions; saved NFL snapshots are read-only evidence."""
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import pytest
from dashboard.football_integrity import (guard_forecasts, reconcile_board_identities,
    resolved_identity, canonical_depth)
from dashboard.availability import recommendation_restriction, kickoff_utc
from dashboard.data import _position_fantasy_points
from dashboard.data import build_start_sit_board
from dashboard.lineup_rules import lineup_status
from src.football_qa import SCORING, validate_board, require_no_hard_errors

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.parametrize('points',[4,6])
def test_stafford_duplicate_reconnects_real_four_game_sample(points):
    # Pin the original defect evidence; refreshed publication data may already
    # have removed the duplicate and must not serve as a historical fixture.
    raw=pd.read_parquet(ROOT/f'tests/fixtures/football_repair_20261009/live_start_sit_board_{points}pt_current.parquet')
    repaired=reconcile_board_identities(raw)
    player=repaired.loc[repaired.player_id.eq('00-0026498')]
    assert len(player)==1 and player.iloc[0].games_played==4
    assert np.isfinite(player.iloc[0].median_ppr)
    assert not repaired.player_id.str.startswith('depth:').any()
    assert player.iloc[0].team=='LA'
    assert not np.isfinite(raw.loc[raw.player_id.eq('depth:matthew stafford'),'median_ppr'].iloc[0])
    assert player.iloc[0].median_ppr==raw.loc[raw.player_id.eq('00-0026498'),'median_ppr'].iloc[0]

@pytest.mark.parametrize('points,name',[(4,'Nick Mullens'),(6,'Nick Mullens'),(4,'Andy Dalton')])
def test_saved_negative_intervals_quarantined_without_clamping(points,name):
    raw=pd.read_parquet(ROOT/f'data/processed/live_start_sit_board_{points}pt_current.parquet')
    row=raw.loc[raw.player.eq(name)]
    guarded=guard_forecasts(row)
    assert not guarded.forecast_valid.any()
    assert not guarded.is_roster_relevant.any()
    pd.testing.assert_series_equal(guarded.median_ppr,row.median_ppr)
    assert (guarded.median_ppr<0).all()

@pytest.mark.parametrize('number',[float('nan'),float('inf'),-float('inf')])
def test_nonfinite_never_actionable(number):
    b=pd.DataFrame([{'floor_ppr':0,'median_ppr':number,'projected_ppr':number,'ceiling_ppr':20,'is_roster_relevant':True}])
    assert not guard_forecasts(b).is_roster_relevant.any()

def test_valid_negative_expected_forecast_is_not_rejected():
    b=pd.DataFrame([{'floor_ppr':-5,'median_ppr':-1,'projected_ppr':-1,'ceiling_ppr':2}])
    assert guard_forecasts(b).forecast_valid.all()

def test_uncertain_names_are_not_automatically_merged():
    assert resolved_identity('Matt Stafford','QB') is None
    assert resolved_identity('Matthew Stafford','WR') is None
    assert resolved_identity('Kyle Pitts Sr.','TE')[0]=='00-0036970'

def test_conflicting_teams_require_explicit_trade_review():
    b=pd.DataFrame([{'player_id':'00-0026498','player':'Matthew Stafford','position':'QB','team':'SEA'},
                    {'player_id':'depth:matthew stafford','player':'Matthew Stafford','position':'QB','team':'LA'}])
    with pytest.raises(ValueError,match='trade review'): reconcile_board_identities(b)

@pytest.mark.parametrize('status',['OUT','IR','PUP','Inactive','Reserve/Injured','Reserve/PUP','Suspended'])
def test_unavailable_status_never_actionable(status):
    assert recommendation_restriction({'injury_status_live':status})=='Unavailable'

def test_questionable_not_equivalent_to_confirmed_out():
    assert recommendation_restriction({'injury_status_live':'Questionable'}) is None
    assert recommendation_restriction({'next_opponent':'BYE'})=='Bye week'

def test_eastern_schedule_not_central_and_dst_correct():
    assert kickoff_utc({'gameday':'2026-10-11','gametime':'13:00'})==datetime(2026,10,11,17,tzinfo=timezone.utc)
    assert kickoff_utc({'gameday':'2026-12-06','gametime':'13:00'})==datetime(2026,12,6,18,tzinfo=timezone.utc)
    assert recommendation_restriction({'gameday':'2026-10-11','gametime':'13:00'},datetime(2026,10,11,17,30,tzinfo=timezone.utc))=='Game locked'

def test_postponed_cannot_claim_ready():
    now=datetime(2026,10,9,17,tzinfo=timezone.utc)
    meta={'refreshed_at':now.isoformat(),'context_refreshed_at':now.isoformat()}
    assert lineup_status([{'player_id':'test','kickoff_at':now,'game_status_live':'Postponed'}],meta,now)=='VERIFY DATA'

def test_complete_fallback_scoring_matches_supported_rules():
    game={k:0 for k in SCORING}
    game.update(passing_tds=1,passing_interceptions=1,sack_fumbles_lost=1,
                receiving_2pt_conversions=1,special_teams_tds=1)
    assert _position_fantasy_points(pd.DataFrame([game])).iloc[0]==8

def test_publication_validator_rejects_invalid_before_writes():
    board=pd.DataFrame([{'player_id':'a','player':'A','floor_ppr':0,'median_ppr':float('inf'),'projected_ppr':float('inf'),'ceiling_ppr':20}])
    with pytest.raises(AssertionError): require_no_hard_errors(validate_board(board))

def test_incomplete_fallback_rejected_instead_of_inventing_zero_categories():
    with pytest.raises(ValueError,match='missing categories'):
        _position_fantasy_points(pd.DataFrame([{'passing_yards':200}]))

def test_provider_id_disagreement_not_merged():
    d=pd.DataFrame([{'player':'Matthew Stafford','player_key':'matthew stafford','depth_position_live':'QB','provider_gsis_id':'wrong'}])
    with pytest.raises(ValueError,match='disagrees'): canonical_depth(d)

def test_thursday_result_does_not_skip_current_week_or_leak_target_stats():
    rows=[{'season':2026,'week':w,'player_id':'a','player_display_name':'A','position':'WR','team':'SEA','opponent_team':'SF','fantasy_points_ppr':10} for w in range(1,5)]
    rows.append({**rows[0],'week':5,'fantasy_points_ppr':100})
    games=pd.DataFrame([{'season':2026,'game_type':'REG','week':5,'home_team':'SEA','away_team':'SF','home_score':None,'away_score':None},
                        {'season':2026,'game_type':'REG','week':6,'home_team':'SEA','away_team':'SF','home_score':None,'away_score':None}])
    board,week=build_start_sit_board(pd.DataFrame(rows),games,2026)
    assert week==5 and board.games_played.iloc[0]==4
    assert board.season_ppr.iloc[0]==10

def test_invalid_forecast_cannot_replace_last_good_snapshot(tmp_path):
    from src.refresh_weekly_snapshot import atomic_parquet
    path=tmp_path/'live_start_sit_board_4pt_current.parquet'
    good=pd.DataFrame([{'player_id':'test','floor_ppr':0,'median_ppr':10,'projected_ppr':10,'ceiling_ppr':20}])
    atomic_parquet(good,path)
    before=path.read_bytes()
    invalid=good.copy(); invalid['median_ppr']=pd.NA
    with pytest.raises(AssertionError): atomic_parquet(invalid,path)
    assert path.read_bytes()==before
