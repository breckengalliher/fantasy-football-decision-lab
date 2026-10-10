import copy
from pathlib import Path

import pandas as pd
import pytest

from dashboard import public_display_cache as cache
from dashboard.presentation import fantasy_game_log, opponent_position_rank


def metadata(revision='a' * 40):
    names = ['live_start_sit_board_4pt_current.parquet', 'live_start_sit_board_6pt_current.parquet',
             'live_weekly_current.parquet', 'live_refresh_metadata.json']
    return {'season': 2026, 'next_week': 5, '_publication': {
        'revision': revision, 'season': 2026, 'week': 5, 'validation_status': 'passed',
        'files': {name: {'sha256': 'b' * 64} for name in names}}}


@pytest.fixture(autouse=True)
def clear():
    cache.clear_public_display_cache()
    yield
    cache.clear_public_display_cache()


@pytest.mark.parametrize('change', ['legacy', 'invalid', 'revision', 'missing_hash', 'season', 'week'])
def test_unverified_or_mutable_publications_bypass_cache(change):
    value = metadata()
    if change == 'legacy': value.pop('_publication')
    elif change == 'invalid': value['_publication']['validation_status'] = 'failed'
    elif change == 'revision': value['_publication']['revision'] = 'main'
    elif change == 'missing_hash': value['_publication']['files'].pop('live_weekly_current.parquet')
    elif change == 'season': value['season'] = 2025
    elif change == 'week': value['next_week'] = 6
    assert cache.public_display_version(value, 4) is None


def test_key_changes_for_publication_asset_hash_and_scoring():
    original = metadata()
    key = cache.public_display_version(original, 4)
    assert key != cache.public_display_version(original, 6)
    assert key != cache.public_display_version(metadata('c' * 40), 4)
    changed = copy.deepcopy(original)
    changed['_publication']['files']['live_weekly_current.parquet']['sha256'] = 'd' * 64
    assert key != cache.public_display_version(changed, 4)


def test_game_log_reused_without_return_value_mutation_leaking(monkeypatch):
    calls = []
    def calculate(weekly, row, points):
        calls.append(points)
        return {'headers': ['Week'], 'rows': [['1', str(points)]]}
    monkeypatch.setattr(cache, 'fantasy_game_log', calculate)
    key = cache.public_display_version(metadata(), 4)
    row = {'player_id': 'stable-id'}
    first = cache.display_game_log(pd.DataFrame(), row, 4, key)
    first['rows'][0][0] = 'private caller edit'
    second = cache.display_game_log(pd.DataFrame(), row, 4, key)
    assert second['rows'][0][0] == '1'
    assert calls == [4]
    cache.display_game_log(pd.DataFrame(), row, 6, cache.public_display_version(metadata(), 6))
    assert calls == [4, 6]


def test_missing_identity_and_legacy_not_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(cache, 'fantasy_game_log', lambda *args: calls.append(True) or {'rows': []})
    key = cache.public_display_version(metadata(), 4)
    for _ in range(2):
        cache.display_game_log(pd.DataFrame(), {'player_id': None}, 4, key)
        cache.display_game_log(pd.DataFrame(), {'player_id': 'stable-id'}, 4, None)
    assert len(calls) == 4


@pytest.mark.parametrize('files', [None, [], 'invalid', {'live_weekly_current.parquet': None}])
def test_malformed_publication_files_bypass_cache(files):
    value = metadata()
    value['_publication']['files'] = files
    assert cache.public_display_version(value, 4) is None


def test_missing_metadata_bypasses_cache():
    assert cache.public_display_version(None, 4) is None


@pytest.mark.parametrize('points', [4, 6])
def test_actual_snapshot_rank_and_log_outputs_remain_identical(points):
    root = Path(__file__).resolve().parents[1] / 'data' / 'processed'
    board = pd.read_parquet(root / f'live_start_sit_board_{points}pt_current.parquet')
    weekly = pd.read_parquet(root / 'live_weekly_current.parquet')
    key = cache.public_display_version(metadata(), points)
    # All existing player records, not only the two showcase quarterbacks.
    for _, row in board.iterrows():
        assert cache.display_opponent_rank(board, row, key) == opponent_position_rank(board, row)
        assert cache.display_game_log(weekly, row, points, key) == fantasy_game_log(weekly, row, points)

