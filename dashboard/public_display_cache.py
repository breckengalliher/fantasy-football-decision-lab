"""Bounded, immutable-publication caches for display-only statistics.

Never accepts an account, roster, or session value. Legacy/mutable snapshots
deliberately bypass these caches. Projections and methodology are unchanged.
"""
import json
import re

import streamlit as st

try:
    from dashboard.presentation import fantasy_game_log, opponent_position_rank, opponent_position_ranks
except ModuleNotFoundError:
    from presentation import fantasy_game_log, opponent_position_rank, opponent_position_ranks


def public_display_version(metadata, passing_td_points):
    if not isinstance(metadata, dict):
        return None
    publication = metadata.get('_publication', {})
    if (not isinstance(publication, dict) or publication.get('validation_status') != 'passed'
            or not re.fullmatch(r'[a-f0-9]{40}', str(publication.get('revision', '')))
            or publication.get('season') != metadata.get('season')
            or publication.get('week') != metadata.get('next_week')
            or passing_td_points not in (4, 6)):
        return None
    names = (f'live_start_sit_board_{passing_td_points}pt_current.parquet',
             'live_weekly_current.parquet', 'live_refresh_metadata.json')
    files = publication.get('files')
    if not isinstance(files, dict) or any(not isinstance(files.get(name), dict) for name in names):
        return None
    hashes = {name: files[name].get('sha256', '') for name in names}
    if not all(re.fullmatch(r'[a-f0-9]{64}', str(value)) for value in hashes.values()):
        return None
    return json.dumps({'revision': publication['revision'], 'files': hashes,
                       'season': metadata['season'], 'week': metadata['next_week'],
                       'passing_td_points': passing_td_points}, sort_keys=True)


@st.cache_data(max_entries=4, ttl=300, show_spinner=False)
def _cached_ranks(version, _board, scope='comparison'):
    # Underscored data frames are intentionally not rehashed on every rerun.
    # The key includes immutable revision + exact verified asset digests.
    return opponent_position_ranks(_board)


def display_ranks(board, version=None, *, scope='comparison'):
    return opponent_position_ranks(board) if version is None else _cached_ranks(version, board, scope)


@st.cache_resource(max_entries=2, show_spinner=False)
def _cached_roster_pool(version, _board):
    return _valid_roster_pool(_board)


def _valid_roster_pool(board):
    return board.loc[board.forecast_valid.eq(True)].copy() if 'forecast_valid' in board else board


def roster_pool(board, version=None):
    # Only public, verified immutable assets enter the cross-session cache.
    # No assignment, owner, preference, or authenticated state is accepted.
    return _valid_roster_pool(board) if version is None else _cached_roster_pool(version, board)


def _comparison_pool(board, positions):
    return board.loc[
        board['position'].isin(positions) & board['next_opponent'].notna()
        & board['is_roster_relevant'] & board['verified_qb_starter']
    ].copy()


@st.cache_resource(max_entries=12, show_spinner=False)
def _cached_comparison_pool(version, positions, _board):
    # Six public position choices in each of two supported scoring formats.
    # Entries stay bounded across revisions; callers only read these frames.
    return _comparison_pool(_board, positions)


def comparison_pool(board, positions, version=None):
    positions = tuple(sorted(positions))
    return (_comparison_pool(board, positions) if version is None
            else _cached_comparison_pool(version, positions, board))


@st.cache_data(max_entries=128, ttl=300, show_spinner=False)
def _cached_game_log(version, player_id, passing_td_points, _weekly, _row):
    return fantasy_game_log(_weekly, _row, passing_td_points)


def display_opponent_rank(board, row, version=None):
    if version is None:
        return opponent_position_rank(board, row)
    return _cached_ranks(version, board).get((str(row.get('position', '')).upper(),
                                             str(row.get('next_opponent', '')).upper()))


def display_game_log(weekly, row, passing_td_points, version=None):
    player_id = str(row.get('player_id', '')).strip()
    if version is None or not player_id or player_id.lower() in ('nan', 'none', '<na>'):
        return fantasy_game_log(weekly, row, passing_td_points)
    return _cached_game_log(version, player_id, passing_td_points, weekly, row)


def clear_public_display_cache():
    _cached_ranks.clear()
    _cached_game_log.clear()
    _cached_roster_pool.clear()
    _cached_comparison_pool.clear()

