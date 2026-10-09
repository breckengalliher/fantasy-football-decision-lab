"""Output equivalence for CPU-only rendering repairs, not new football policy."""
from pathlib import Path

import pandas as pd
import pytest

from dashboard.command_center_v2 import _player_lookup, _matchup_chip
from dashboard.presentation import opponent_position_rank, opponent_position_ranks


def original_rank(board, row):
    # Frozen pre-repair algorithm: compare against the old policy, not the new
    # wrapper. This deliberately retains its normalization and tie semantics.
    position = str(row.get('position', '')).upper()
    opponent = str(row.get('next_opponent', '')).upper()
    if not position or not opponent or not {'position','next_opponent','schedule_adjusted_index'}.issubset(board.columns):
        return None
    peers = board.loc[board.position.astype(str).str.upper().eq(position), ['next_opponent','schedule_adjusted_index']].copy()
    peers['next_opponent'] = peers.next_opponent.astype(str).str.upper()
    peers['schedule_adjusted_index'] = pd.to_numeric(peers.schedule_adjusted_index, errors='coerce')
    peers = peers.dropna().groupby('next_opponent', as_index=False).schedule_adjusted_index.median()
    if peers.empty or opponent not in set(peers.next_opponent): return None
    peers = peers.sort_values(['schedule_adjusted_index','next_opponent']).reset_index(drop=True)
    peers['rank'] = peers.schedule_adjusted_index.rank(method='min').astype(int)
    rank = int(peers.loc[peers.next_opponent.eq(opponent)].iloc[0]['rank'])
    total = len(peers)
    band = max(1, round(total*.31))
    tone, label = ('tough','Tough matchup') if rank <= band else (('favorable','Favorable matchup') if rank > total-band else ('neutral','Neutral matchup'))
    return dict(rank=rank,total=total,tone=tone,label=label,position=position,opponent=opponent)


@pytest.mark.parametrize('points',[4,6])
def test_all_published_rank_and_chip_outputs_match_frozen_policy(points):
    root = Path(__file__).resolve().parents[1]
    board = pd.read_parquet(root/f'data/processed/live_start_sit_board_{points}pt_current.parquet')
    before = board.copy(deep=True)
    ranks = opponent_position_ranks(board)
    for row in board.to_dict('records'):
        expected = original_rank(board,row)
        assert opponent_position_rank(board,row) == expected
        assert ranks.get((str(row['position']).upper(),str(row['next_opponent']).upper())) == expected
        assert _matchup_chip(board,row,ranks) == _matchup_chip(board,row)
    pd.testing.assert_frame_equal(board,before)


def test_rank_ties_missing_numeric_and_normalization_preserved():
    board = pd.DataFrame([
        dict(position='wr',next_opponent='sf',schedule_adjusted_index='0.8'),
        dict(position='WR',next_opponent='GB',schedule_adjusted_index=.8),
        dict(position='WR',next_opponent='TB',schedule_adjusted_index='bad'),
        dict(position='RB',next_opponent='SF',schedule_adjusted_index=1.1),
        dict(position='RB',next_opponent='GB',schedule_adjusted_index=None),
    ])
    ranks=opponent_position_ranks(board)
    for row in board.to_dict('records'):
        assert ranks.get((row['position'].upper(),row['next_opponent'].upper())) == original_rank(board,row)
    assert ranks[('WR','SF')]['rank'] == ranks[('WR','GB')]['rank'] == 1
    assert opponent_position_ranks(pd.DataFrame()) == {}


def test_batch_lookup_preserves_values_duplicates_and_input():
    pool=pd.DataFrame([dict(player_id=1,median_ppr=12.3,available=True,player='A'),
                       dict(player_id=1,median_ppr=14.2,available=False,player='B')])
    before=pool.copy(deep=True)
    old={str(row['player_id']):row.to_dict() for _,row in pool.iterrows()}
    assert _player_lookup(pool) == old
    pd.testing.assert_frame_equal(pool,before)
    assert _player_lookup(pool.iloc[:0]) == {}


def test_roster_lookup_is_only_a_selection_not_a_projection_change():
    pool = pd.DataFrame([dict(player_id='a',median_ppr=14.2),dict(player_id='b',median_ppr=9.4)])
    all_rows = _player_lookup(pool)
    assert _player_lookup(pool, {'b','missing'}) == {'b':all_rows['b']}
    assert _player_lookup(pool, set()) == {}
