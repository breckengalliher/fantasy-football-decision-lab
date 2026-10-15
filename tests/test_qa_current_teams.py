import pandas as pd
import pytest
from datetime import datetime, timezone
from src.qa_current_teams import TRANSACTIONS, reviewed_current_teams
from dashboard.data import build_start_sit_board


def history():
    return pd.DataFrame([dict(player_id=e['player_id'],player_display_name=e['player'],
        position=e['position'],recent_team=e['old'],week=5,season=2026,
        opponent_team='SEA',fantasy_points_ppr=5.,receptions=2,receiving_yards=20,receiving_tds=0,
        carries=2,targets=3,rushing_yards=10,rushing_tds=0) for e in TRANSACTIONS])


def fetch(key,url):
    e=next(e for e in TRANSACTIONS if e['url']==url)
    return ('<p>'+' '.join(e['anchors'])+'</p>').encode()


def test_reviewed_mapping_does_not_edit_game_logs():
    data=history(); original=data.copy(deep=True)
    mapping=reviewed_current_teams(data,2026,6,fetch)
    assert mapping=={e['player_id']:e['new'] for e in TRANSACTIONS}
    pd.testing.assert_frame_equal(data,original)


@pytest.mark.parametrize('kind',['period','source','identity','future'])
def test_evidence_conflicts_fail_closed(kind):
    data=history(); week=6; getter=fetch; at=datetime(2026,10,14,tzinfo=timezone.utc)
    if kind=='period': week=7
    if kind=='source': getter=lambda *args:b'unrelated article'
    if kind=='identity': data.loc[0,'player_display_name']='Different player'
    if kind=='future': at=datetime(2026,10,8,tzinfo=timezone.utc)
    with pytest.raises(ValueError): reviewed_current_teams(data,2026,week,getter,at)


def test_upcoming_team_changes_not_historical_production():
    data=history(); original=data.copy(deep=True)
    schedules=pd.DataFrame([dict(season=2026,week=6,home_team='HOU',away_team='JAX'),
        dict(season=2026,week=6,home_team='ARI',away_team='LA'),
        dict(season=2026,week=6,home_team='WAS',away_team='SF')])
    baseline,_=build_start_sit_board(data,schedules,2026)
    repaired,_=build_start_sit_board(data,schedules,2026,current_teams={'00-0039849':'HOU'})
    before=baseline.set_index('player_id'); after=repaired.set_index('player_id')
    assert after.loc['00-0039849','next_opponent']=='JAX'
    assert before.loc['00-0039849','next_opponent']=='LA'
    pd.testing.assert_series_equal(before.season_ppr,after.season_ppr)
    pd.testing.assert_frame_equal(data,original)
    unchanged=before.index.difference(['00-0039849'])
    pd.testing.assert_frame_equal(before.loc[unchanged],after.loc[unchanged])


def test_invalid_mapping_rejected():
    schedules=pd.DataFrame([dict(season=2026,week=6,home_team='ARI',away_team='LA')])
    with pytest.raises(ValueError,match='assignment'):
        build_start_sit_board(history(),schedules,2026,current_teams={'missing':'ARI'})
