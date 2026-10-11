"""Exercise the offered replacement editor through real Streamlit reruns."""
import pytest
from streamlit.testing.v1 import AppTest


SCRIPT = '''
from datetime import datetime, timezone
from types import SimpleNamespace
import streamlit as st
from dashboard.command_center_v2 import _entry, _replacements, _show_save_notice
from dashboard.lineup_rules import build_lineup_actions
from dashboard.repositories.rosters import RosterRepository
from dashboard.supabase_api import SupabaseAPIError
now = datetime(2026,10,10,tzinfo=timezone.utc)
lookup = {
 'p1': {'position':'QB','player':'Starter','median_ppr':15,'projected_ppr':15,'floor_ppr':5,'ceiling_ppr':25,'injury_status_live':'Out'},
 'p2': {'position':'QB','player':'Bench','median_ppr':20,'projected_ppr':20,'floor_ppr':10,'ceiling_ppr':30,'injury_status_live':'Available'},
}
slots = [
 {'id':'qb','slot_type':'QB','slot_order':0,'is_starter':True,'roster_assignments':[{'id':'a','player_id':'p1','updated_at':'2026-10-10T18:00:00+00:00'}]},
 {'id':'bench','slot_type':'BENCH','slot_order':0,'is_starter':False,'roster_assignments':[{'id':'b','player_id':'p2','updated_at':'2026-10-10T18:00:01+00:00'}]},
]
if st.session_state.get('missing_version'): slots[1]['roster_assignments'][0].pop('updated_at')
class API:
 def rpc(self, token, name, payload):
  if st.session_state.get('reject_write'): raise SupabaseAPIError('Roster changed; reload before saving')
  st.session_state['committed_payload']=payload
repo=RosterRepository(API(),'ordinary-user-token','owner')
entries=[_entry(s,lookup,now) for s in slots]
_show_save_notice('team')
_replacements({'id':'team'},repo,build_lineup_actions(entries[:1],now),entries[:1],entries[1:],lookup,context_verified=st.session_state.get('verified',True))
'''


@pytest.mark.parametrize('failure', [None, 'missing_version', 'reject_write'])
def test_replacement_preserves_both_versions_and_acknowledges_only_commit(failure):
    app = AppTest.from_string(SCRIPT)
    if failure:
        app.session_state[failure] = True
    app.run()
    assert not app.exception
    app.checkbox[0].check().run()
    app.button(key='cc_apply_replacement_qb_p2').click().run()
    assert not app.exception
    if failure:
        assert app.error
        assert 'committed_payload' not in app.session_state
        assert not app.get('toast')
    else:
        payload = app.session_state['committed_payload']
        assert payload['p_first_updated_at'] == '2026-10-10T18:00:00+00:00'
        assert payload['p_second_updated_at'] == '2026-10-10T18:00:01+00:00'
        assert app.get('toast')


def test_unverified_availability_never_offers_replacement_or_apply_control():
    app = AppTest.from_string(SCRIPT)
    app.session_state['verified'] = False
    app.run()
    assert not app.exception
    assert not app.button and not app.checkbox
    assert 'VERIFY DATA' in app.info[0].value


def test_add_or_removed_assignment_invalidates_pending_editor_before_submit():
    from dashboard.roster_edit_guard import edit_is_current, reject_changed_editors
    roster = [{'id':'slot', 'slot_type':'BENCH', 'slot_order':0,
               'roster_assignments':[]}]
    state = {'cc_add_panel_team_slot':True, 'cc_slot_pick_team_slot':'old-pick'}
    edit_is_current(state, 'cc_add_revision_team_slot', roster)
    changed = [{**roster[0], 'roster_assignments':[{'id':'new','player_id':'new-pick','updated_at':'v1'}]}]
    assert reject_changed_editors(state, 'team', changed)
    assert state['cc_add_panel_team_slot'] is False
    assert 'cc_slot_pick_team_slot' not in state
    assert not reject_changed_editors(state, 'team', changed)
    state = {'cc_manage_new':True, 'cc_confirm_remove_new':True}
    edit_is_current(state, 'cc_edit_revision_team_new', changed)
    assert reject_changed_editors(state, 'team', roster)
    assert state['cc_manage_new'] is False
    assert 'cc_confirm_remove_new' not in state
