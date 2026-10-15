"""Actual Streamlit UI rerun; local only, no credentials or provider calls."""
from streamlit.testing.v1 import AppTest
from dashboard import auth_storage as bridge


def test_retry_widget_preserves_draft_and_stops_at_bound(monkeypatch):
    monkeypatch.setenv('RENDER_SERVICE_ID', 'srv-db4ir249v7es7389sshg')
    monkeypatch.setattr(bridge, '_bridge', lambda **kwargs: None)
    app = AppTest.from_string('''
import streamlit as st
from types import SimpleNamespace
from dashboard.auth_storage import browser_auth_storage
st.session_state.setdefault('draft', 'unsaved test selection')
browser_auth_storage(SimpleNamespace(url='https://deburhwrnuqeyexpezzo.supabase.co', publishable_key='sb_publishable_test'))
st.text(st.session_state['draft'])
''').run(timeout=10)
    assert not app.exception
    for attempt in range(1, 4):
        app.button(key='cc_retry_auth_bridge').click().run(timeout=10)
        assert not app.exception
        assert app.session_state['_cc_auth_bridge_mount_attempt'] == attempt
        assert app.session_state['draft'] == 'unsaved test selection'
    assert len(app.button) == 0
    assert 'still unavailable' in app.warning[0].value
