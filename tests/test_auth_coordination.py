"""Server adoption checks; browser lock tests live in auth_bridge.test.cjs."""
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import base64
import json
import time
from dashboard import auth_ui, auth_storage
from dashboard.supabase_api import AuthSession, SupabaseAPIError


def session(user='a', exp=None, refresh='new'):
    payload = base64.urlsafe_b64encode(json.dumps({'exp': exp or time.time()+3600,'session_id':'family-'+user}).encode()).decode().rstrip('=')
    return AuthSession('fake.'+payload+'.unsigned',refresh,3600,user,user+'@example.test')


def setup(monkeypatch, existing=None, shared=None):
    state={'cc_pending_edit':'retain','cc_selected_team':'saved-team'}
    if existing:state.update({auth_ui.SESSION_KEY:asdict(existing),'command_center_persistence_mode':'always'})
    mock=SimpleNamespace(session_state=state,query_params={'team':'saved-team'},warning=lambda _:None,button=lambda *a,**k:False,rerun=lambda:None)
    monkeypatch.setattr(auth_ui,'st',mock)
    monkeypatch.setattr(auth_storage,'st',mock)
    record={'version':2,'revision':'new','mode':'always','expires_at':None,'session':asdict(shared)} if shared else None
    storage=auth_storage.AuthStorage({auth_storage.RECORD_KEY:record} if record else {})
    api=SimpleNamespace(user=lambda token:{'id':shared.user_id},refresh=lambda _:(_ for _ in ()).throw(AssertionError('server must not rotate shared token')))
    return state,storage,api


def test_imports_are_exact_isolated_source():
    assert Path(auth_ui.__file__).resolve().parents[1] == Path(__file__).resolve().parents[1]


def test_pending_widget_survives_temporary_auth_gate():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
import streamlit as st
from dashboard.auth_ui import _retain_pending_roster_inputs
_retain_pending_roster_inputs()
if not st.session_state.get('auth_waiting', False):
    st.selectbox('Pending destination', ['bench-1', 'bench-2'], key='cc_target_assignment')
    st.button('Save', key='cc_move_assignment')
else:
    st.caption('Restoring your private session')
''').run()
    app.selectbox[0].select('bench-2').run()
    app.session_state['auth_waiting'] = True
    app.run()
    assert not app.exception
    app.session_state['auth_waiting'] = False
    app.run()
    assert not app.exception
    assert app.selectbox[0].value == 'bench-2'


def test_stale_tab_adopts_latest_verified_session_and_preserves_edits(monkeypatch):
    old=session(exp=1,refresh='old');new=session()
    state,storage,api=setup(monkeypatch,old,new)
    assert auth_ui.restore_session(api,storage)==new
    assert state['cc_pending_edit']=='retain'
    assert auth_ui.st.query_params['team']=='saved-team'


def test_refresh_is_queued_in_browser_not_stale_server_token(monkeypatch):
    old=session(exp=1,refresh='old')
    state,storage,api=setup(monkeypatch,old,old)
    assert auth_ui.restore_session(api,storage) is None
    assert state[auth_storage.PENDING_KEY]['refresh']
    assert state['cc_pending_edit']=='retain'


def test_new_tab_restores_by_provider_verified_access_without_rotation(monkeypatch):
    new=session();state,storage,api=setup(monkeypatch,shared=new)
    assert auth_ui.restore_session(api,storage)==new


def test_logout_in_other_tab_blocks_even_unexpired_python_session(monkeypatch):
    state,storage,api=setup(monkeypatch,existing=session())
    assert auth_ui.restore_session(api,storage) is None
    assert auth_ui.SESSION_KEY not in state
    assert 'cc_pending_edit' not in state


def test_account_switch_clears_previous_private_ui_before_adoption(monkeypatch):
    state,storage,api=setup(monkeypatch,session('a'),session('b'))
    assert auth_ui.restore_session(api,storage).user_id=='b'
    assert 'cc_pending_edit' not in state
    assert 'team' not in auth_ui.st.query_params


def test_shared_identity_must_match_provider(monkeypatch):
    state,storage,api=setup(monkeypatch,session('a'),session('b'))
    api.user=lambda token:{'id':'wrong'}
    assert auth_ui.restore_session(api,storage) is None
    assert auth_ui.SESSION_KEY not in state
    assert state[auth_storage.PENDING_KEY]['clear']


def test_transient_verification_failure_preserves_pending_edits(monkeypatch):
    state,storage,api=setup(monkeypatch,session(exp=1),session())
    def fail(_):raise SupabaseAPIError('Unavailable',retryable=True)
    api.user=fail
    assert auth_ui.restore_session(api,storage) is None
    assert state['cc_pending_edit']=='retain'
    assert storage.getItem(auth_storage.RECORD_KEY)


def test_browser_outage_does_not_loop_refresh_requests(monkeypatch):
    state,storage,api=setup(monkeypatch,session(exp=1),session(exp=1))
    storage.auth_result={'status':'retryable'}
    assert auth_ui.restore_session(api,storage) is None
    assert auth_storage.PENDING_KEY not in state
    assert state['cc_pending_edit']=='retain'
