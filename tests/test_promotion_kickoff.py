import pandas as pd
import pytest
from dashboard.providers.sportsdataio import SportsDataIOContext, add_depth_chart_promotions, normalize_depth_charts

@pytest.mark.parametrize('second_time,expected', [('13:00','13:00'),('16:25',None),(None,'13:00')])
def test_promotion_uses_only_agreeing_complete_same_game_schedule(second_time,expected):
    board=pd.DataFrame([
        {'player_id':'a','player':'Anchor A','position':'WR','team':'SEA','next_opponent':'SF','gameday':'2026-10-11','gametime':'13:00','median_ppr':12.,'recent_opportunities':8.,'is_roster_relevant':True},
        {'player_id':'b','player':'Anchor B','position':'WR','team':'SEA','next_opponent':'SF','gameday':'2026-10-11','gametime':second_time,'median_ppr':12.,'recent_opportunities':8.,'is_roster_relevant':True},
        {'player_id':'c','player':'Other Game','position':'WR','team':'SEA','next_opponent':'ARI','gameday':'2026-10-12','gametime':'20:15','median_ppr':12.,'recent_opportunities':8.,'is_roster_relevant':True},
    ])
    context=SportsDataIOContext(injuries=pd.DataFrame(),games=pd.DataFrame([{'team':'SEA','provider_opponent':'SF'}]),depth_charts=normalize_depth_charts([{'Name':'Promoted Receiver','Team':'SEA','Position':'WR','DepthOrder':2}]),refreshed_at='2026-10-11T12:00:00Z')
    out=add_depth_chart_promotions(board,context)
    row=out.loc[out.player.eq('Promoted Receiver')].iloc[0]
    if expected is None:
        assert pd.isna(row.gameday) and pd.isna(row.gametime)
    else:
        assert row.gameday=='2026-10-11' and row.gametime==expected
    preserved=[column for column in board.columns if column not in ('gameday','gametime')]
    pd.testing.assert_frame_equal(out.loc[out.player_id.isin(board.player_id),preserved].reset_index(drop=True),board[preserved],check_dtype=False)
    if second_time is None:
        assert out.loc[out.player_id.eq('b'),'gametime'].iloc[0]=='13:00'
    assert row.median_ppr==pytest.approx(11.568)
