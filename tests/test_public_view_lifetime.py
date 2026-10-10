"""Public cache lifetime, isolation and lazy roster controls."""
import ast
import copy
import json
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.testing.v1 import AppTest

from dashboard import public_display_cache as cache


def metadata():
    names = ['live_refresh_metadata.json', 'live_weekly_current.parquet',
             'live_start_sit_board_4pt_current.parquet', 'live_start_sit_board_6pt_current.parquet']
    return dict(season=2026, next_week=5, publication_status='validated',
                _publication=dict(revision='a' * 40, season=2026, week=5, validation_status='passed',
                                  files={name: dict(sha256='b' * 64) for name in names}))


def snapshot_functions():
    source = Path(__file__).parents[1].joinpath('dashboard/app.py').read_text(encoding='utf8')
    names = {'_immutable_published_snapshot', '_legacy_published_snapshot',
             'get_published_snapshot', 'clear_published_snapshot'}
    tree = ast.Module(body=[node for node in ast.parse(source).body
                           if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    calls = []
    def load(season, points, value):
        calls.append((season, points, value))
        return object()
    namespace = dict(st=st, json=json, public_display_version=cache.public_display_version,
                     _load_published_snapshot=load, __name__='snapshot_lifetime_test')
    exec(compile(tree, '<snapshot_lifetime>', 'exec'), namespace)
    namespace['clear_published_snapshot']()
    return namespace, calls


def test_immutable_snapshot_reuse_format_revision_and_bounded_eviction():
    functions, calls = snapshot_functions()
    get = functions['get_published_snapshot']
    value = metadata()
    first = get(2026, 4, json.dumps(value))
    assert get(2026, 4, json.dumps(value, sort_keys=True)) is first
    assert get(2026, 6, json.dumps(value)) is not first
    changed = copy.deepcopy(value)
    changed['_publication']['files']['live_start_sit_board_4pt_current.parquet']['sha256'] = 'c' * 64
    assert get(2026, 4, json.dumps(changed)) is not first
    assert len(calls) == 3
    assert get(2026, 4, json.dumps(value)) is not first  # max two verified entries
    functions['clear_published_snapshot']()
    assert get(2026, 4, json.dumps(value)) is not first
    functions['clear_published_snapshot']()


def test_mutable_metadata_cannot_hit_verified_resource():
    functions, calls = snapshot_functions()
    value = metadata()
    verified = functions['get_published_snapshot'](2026, 4, json.dumps(value))
    value['publication_status'] = 'legacy-unverified'
    legacy = functions['get_published_snapshot'](2026, 4, json.dumps(value))
    assert legacy is not verified and len(calls) == 2
    functions['clear_published_snapshot']()


def test_verified_lifetime_outlasts_legacy_expiry(monkeypatch):
    from streamlit.runtime.caching import cache_utils
    st.cache_resource.clear()
    clock = [0.0]
    monkeypatch.setattr(cache_utils, 'TTLCACHE_TIMER', lambda: clock[0])
    functions, calls = snapshot_functions()
    value = metadata()
    get = functions['get_published_snapshot']
    verified = get(2026, 4, json.dumps(value))
    value['publication_status'] = 'legacy-unverified'
    legacy = get(2026, 4, json.dumps(value))
    clock[0] = 301.0
    assert get(2026, 4, json.dumps(value)) is not legacy
    value['publication_status'] = 'validated'
    assert get(2026, 4, json.dumps(value)) is verified
    assert len(calls) == 3
    st.cache_resource.clear()


def test_roster_filter_and_rank_scope_do_not_cross_public_views(monkeypatch):
    cache.clear_public_display_cache()
    board = pd.DataFrame(dict(player_id=['valid', 'invalid'], forecast_valid=[True, False],
                              position=['QB', 'QB'], next_opponent=['A', 'B'], schedule_adjusted_index=[1., 2.]))
    original = board.copy(deep=True)
    version = cache.public_display_version(metadata(), 4)
    roster = cache.roster_pool(board, version)
    assert roster.player_id.tolist() == ['valid']
    assert cache.roster_pool(board, version) is roster
    assert cache.roster_pool(board) is not cache.roster_pool(board)
    assert cache.display_ranks(board, version)[('QB', 'A')]['total'] == 2
    assert cache.display_ranks(roster, version, scope='valid-roster')[('QB', 'A')]['total'] == 1
    pd.testing.assert_frame_equal(board, original)
    cache.clear_public_display_cache()


def test_closed_add_panel_does_not_build_or_retain_player_choices():
    app = AppTest.from_string('''
from dashboard.command_center_v2 import _add_player_slot
class NoRead:
    def __getitem__(self, key): raise AssertionError('Closed control read the player pool')
_add_player_slot(dict(id='team'), [], dict(id='slot',slot_type='QB',slot_order=0), None, NoRead())
''').run()
    assert not app.exception
    assert len(app.expander) == 1
    assert not app.selectbox


def test_open_add_panel_renders_compact_eligible_choices_without_used_player():
    app = AppTest.from_string('''
import pandas as pd
import streamlit as st
from dashboard.command_center_v2 import _add_player_slot
st.session_state['cc_add_panel_team_slot'] = True
pool = pd.DataFrame(dict(player_id=['saved','new','wrong'], player=['Saved','New','Wrong'],
                         team=['A','B','C'],position=['QB','QB','WR'],median_ppr=[25.,20.,30.]))
_add_player_slot(dict(id='team'), [dict(roster_assignments=[dict(player_id='saved')])],
                 dict(id='slot',slot_type='QB',slot_order=0), None, pool)
''').run()
    assert not app.exception
    assert app.selectbox[0].options == ['New · B QB · 20.0 PPR']
    assert app.selectbox[0].value is None
