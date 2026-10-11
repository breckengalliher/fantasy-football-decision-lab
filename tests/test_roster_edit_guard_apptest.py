"""Real Streamlit reruns keep confirmation bound to the displayed roster."""
import copy
import pytest
from streamlit.testing.v1 import AppTest

SCRIPT = '''
import streamlit as st
from types import SimpleNamespace
from unittest.mock import patch
import dashboard.command_center_v2 as ui
from dashboard.command_center_v2 import _manage_player
if 'fixture' not in st.session_state:
    st.session_state.fixture = [
        dict(id='qb',slot_type='QB',slot_order=0,is_starter=True,
             roster_assignments=[dict(id='a',player_id='allen',updated_at='v1')]),
        dict(id='bench',slot_type='BENCH',slot_order=0,is_starter=False,
             roster_assignments=[dict(id='b',player_id='stafford',updated_at='v1')])]
def swap(*args):
    st.session_state['swap_calls'] = st.session_state.get('swap_calls', 0) + 1
    st.stop()  # Stop at the repository boundary; no fake backend write or rerun loop.
roster = st.session_state.fixture
source = next(s for s in roster if s['roster_assignments'][0]['id']=='a')
current = source['roster_assignments'][0]
with patch.object(ui, '_player_locked', lambda *args: False):
    _manage_player(dict(id='team'), roster, source, current,
        SimpleNamespace(swap_players=swap), None,
        dict(allen=dict(position='QB'),stafford=dict(position='QB')))
'''


def test_real_rerun_rejects_stale_move_before_repository_call():
    app = AppTest.from_string(SCRIPT).run()
    assert not app.exception
    roster = copy.deepcopy(app.session_state['fixture'])
    roster[0]['roster_assignments'],roster[1]['roster_assignments'] = roster[1]['roster_assignments'],roster[0]['roster_assignments']
    app.session_state['fixture'] = roster
    next(b for b in app.button if b.label=='Confirm lineup move').click().run()
    assert not app.exception
    assert len(app.warning)==1
    assert 'changed in another visit' in app.warning[0].value
    assert 'swap_calls' not in app.session_state


def test_real_rerun_allows_current_move():
    app = AppTest.from_string(SCRIPT).run()
    next(b for b in app.button if b.label=='Confirm lineup move').click().run()
    assert not app.exception
    assert app.session_state['swap_calls']==1
    assert not app.warning


COMPACT_SCRIPT = '''
import streamlit as st
import pandas as pd
from types import SimpleNamespace
from dashboard.command_center_v2 import _compact_roster_editor, _show_save_notice
from dashboard.roster_edit_guard import reject_changed_editors
if 'fixture' not in st.session_state:
    st.session_state.fixture = [
        dict(id='qb',slot_type='QB',slot_order=0,is_starter=True,roster_assignments=[]),
        dict(id='bench',slot_type='BENCH',slot_order=0,is_starter=False,
             roster_assignments=[dict(id='a',player_id='allen',updated_at='v1')])]
def assign(team, slot, player):
    st.session_state['add_calls'] = st.session_state.get('add_calls', 0) + 1
    if st.session_state.get('fail_save'):
        from dashboard.supabase_api import SupabaseAPIError
        raise SupabaseAPIError('Roster changed; reload before saving')
    st.session_state.fixture[0]['roster_assignments'] = [dict(id='new',player_id=player,updated_at='v2')]
roster = st.session_state.fixture
_show_save_notice('team')
if reject_changed_editors(st.session_state, 'team', roster):
    st.warning('Your lineup changed in another visit. Your stale edit was not applied.')
    st.stop()
pool = pd.DataFrame([dict(player_id='stafford',player='Matthew Stafford',team='LA',position='QB',median_ppr=20)])
_compact_roster_editor(dict(id='team'), roster,
    [s for s in roster if not s['roster_assignments']], SimpleNamespace(assign_player=assign), pool, pd.DataFrame(), 4, {})
'''


@pytest.mark.parametrize('change', ['other_version', 'destination_occupied'])
def test_compact_add_rejects_stale_selection_before_repository_call(change):
    app = AppTest.from_string(COMPACT_SCRIPT).run()
    app.selectbox[0].select('stafford').run()
    assert not app.exception
    roster = copy.deepcopy(app.session_state['fixture'])
    if change == 'destination_occupied':
        roster[0]['roster_assignments'] = [dict(id='other',player_id='goff',updated_at='v2')]
    else:
        roster[1]['roster_assignments'][0]['updated_at'] = 'v2'
    app.session_state['fixture'] = roster
    next(b for b in app.button if b.label == 'Add').click().run()
    assert not app.exception
    assert any('stale edit was not applied' in w.value for w in app.warning)
    assert 'add_calls' not in app.session_state
    assert app.session_state['fixture'] == roster
    assert 'cc_compact_pick_team_qb' not in app.session_state


def test_compact_selection_itself_is_bound_to_the_roster_that_was_displayed():
    app = AppTest.from_string(COMPACT_SCRIPT).run()
    roster = copy.deepcopy(app.session_state['fixture'])
    roster[1]['roster_assignments'][0]['updated_at'] = 'v2'
    app.session_state['fixture'] = roster
    app.selectbox[0].select('stafford').run()
    assert not app.exception
    assert app.warning
    assert 'add_calls' not in app.session_state


@pytest.mark.parametrize('failure', [False, True])
def test_compact_current_add_only_acknowledges_successful_commit(failure):
    app = AppTest.from_string(COMPACT_SCRIPT).run()
    app.selectbox[0].select('stafford').run()
    app.session_state['fail_save'] = failure
    next(b for b in app.button if b.label == 'Add').click().run()
    assert not app.exception
    assert app.session_state['add_calls'] == 1
    assert not app.warning
    assert bool(app.toast) is not failure
    assert bool(app.error) is failure
    if failure:
        assert not app.session_state['fixture'][0]['roster_assignments']
    else:
        assert app.session_state['fixture'][0]['roster_assignments'][0]['player_id'] == 'stafford'
