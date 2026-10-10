"""Real Streamlit reruns keep confirmation bound to the displayed roster."""
import copy
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
