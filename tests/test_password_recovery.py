from pathlib import Path
import pytest
from dashboard.supabase_api import SupabaseAPI
from dashboard import auth_storage
from dashboard import auth_ui


def test_recovery_redirect_uses_documented_query_parameter(monkeypatch):
    api=SupabaseAPI('https://qa.example','public')
    calls=[]
    monkeypatch.setattr(api,'_request',lambda *a,**kw:calls.append((a,kw)))
    api.recover('fixture@example.com','https://staging.example/?recovery=1')
    assert calls[0][1]['params']=={'redirect_to':'https://staging.example/?recovery=1'}
    assert calls[0][1]['json']=={'email':'fixture@example.com'}


def test_password_update_requires_user_authorization_and_minimum_length(monkeypatch):
    api=SupabaseAPI('https://qa.example','public')
    calls=[]
    monkeypatch.setattr(api,'_request',lambda *a,**kw:calls.append((a,kw)))
    with pytest.raises(ValueError):api.update_password('ordinary-token','short')
    assert not calls
    api.update_password('ordinary-token','a-fake-test-password')
    assert calls[0][0]==('PUT','/auth/v1/user')
    assert calls[0][1]['access_token']=='ordinary-token'


def test_bridge_keeps_recovery_separate_from_persistent_storage(monkeypatch):
    monkeypatch.setattr(auth_storage.st,'session_state',{})
    monkeypatch.setattr(auth_storage,'_bridge',lambda **kwargs:{'ok':True,'values':{},
        'recovery':{'type':'recovery','refresh_token':'fixture-only'}})
    storage=auth_storage.browser_auth_storage()
    assert storage.recovery['type']=='recovery'
    assert 'refresh_token' not in storage.storedItems


def test_bridge_rejects_cross_origin_and_removes_link_credentials():
    html=(Path(__file__).parents[1]/'dashboard/components/auth_storage/index.html').read_text()
    assert 'event.origin !== location.origin' in html
    assert "...extra}, location.origin)" in html
    assert 'parent.history.replaceState' in html
    assert 'if (args.clear_recovery) recovery = undefined' in html


def test_verified_link_shows_password_form_without_roster_access(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setattr(auth_ui,'browser_auth_storage',lambda:
        auth_storage.AuthStorage({},recovery={'type':'recovery','refresh_token':'fixture-only'}))
    script='''
import streamlit as st
from dashboard.auth_ui import render_auth
from dashboard.supabase_api import AuthSession
class FakeAPI:
    def refresh(self,token):
        return AuthSession('fake-access','fake-refresh',3600,'fixture-user','fixture@example.com')
    def update_password(self,token,password):
        st.session_state['test_update_length']=len(password)
session=render_auth(FakeAPI(),'https://staging.example')
if session:st.error('Unexpected roster access')
'''
    # This is a functional security test, not a latency benchmark. Allow cold
    # Streamlit initialization under concurrent local Windows/container tests.
    app=AppTest.from_string(script, default_timeout=15).run()
    assert not app.exception
    assert [x.label for x in app.text_input]==['New password','Confirm new password']
    app.text_input[0].set_value('a-fake-test-password')
    app.text_input[1].set_value('different-test-password')
    app.button[0].click().run()
    assert any('do not match' in x.value for x in app.error)
    assert 'test_update_length' not in app.session_state
    assert not app.exception
