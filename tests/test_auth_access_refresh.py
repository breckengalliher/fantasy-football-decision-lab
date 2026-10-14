"""Synthetic auth expiry/control-flow tests, not hosted browser evidence."""
import base64
from dataclasses import asdict
import json
from types import SimpleNamespace
from datetime import datetime, timezone

from dashboard import auth_ui
from dashboard.supabase_api import AuthSession, SupabaseAPIError


def token(exp):
    payload = base64.urlsafe_b64encode(json.dumps({'exp': exp}).encode()).decode().rstrip('=')
    return 'synthetic.' + payload + '.not-a-real-signature'


class Storage:
    def __init__(self):
        self.values = {auth_ui.STORAGE_KEY: 'synthetic-refresh', auth_ui.PERSISTENCE_KEY: 'always'}
    def getItem(self, key): return self.values.get(key)
    def setItem(self, item_key, value, **kwargs): self.values[item_key] = value
    def deleteItem(self, item_key, **kwargs): self.values.pop(item_key, None)


def setup(monkeypatch, expiry):
    existing = AuthSession(token(expiry), 'synthetic-refresh', 3600, 'qa-user', 'qa@example.test')
    state = {auth_ui.SESSION_KEY: asdict(existing), 'cc_unsaved_edit': 'preserve', 'command_center_persistence_mode': 'always'}
    monkeypatch.setattr(auth_ui, 'st', SimpleNamespace(session_state=state, query_params={'team': 'private-team'}, warning=lambda _: None,
                       button=lambda *a, **k: False, rerun=lambda: None))
    return existing, state, Storage()


def test_expired_open_session_refreshes_before_private_use(monkeypatch):
    existing, state, storage = setup(monkeypatch, 1)
    refreshed = AuthSession(token(4_000_000_000), 'rotated-refresh', 3600, existing.user_id, existing.email)
    calls = []
    api = SimpleNamespace(refresh=lambda t: calls.append(t) or refreshed)
    assert auth_ui.restore_session(api, storage) == refreshed
    assert calls == ['synthetic-refresh']
    assert state['cc_unsaved_edit'] == 'preserve'
    assert storage.values[auth_ui.STORAGE_KEY] == 'rotated-refresh'


def test_valid_session_avoids_unnecessary_refresh(monkeypatch):
    existing, state, storage = setup(monkeypatch, 4_000_000_000)
    api = SimpleNamespace(refresh=lambda _: (_ for _ in ()).throw(AssertionError('unexpected refresh')))
    assert auth_ui.restore_session(api, storage) == existing


def test_retryable_refresh_blocks_private_use_without_discarding_credential(monkeypatch):
    existing, state, storage = setup(monkeypatch, 1)
    def fail(_): raise SupabaseAPIError('Temporary outage', retryable=True)
    assert auth_ui.restore_session(SimpleNamespace(refresh=fail), storage) is None
    assert storage.values[auth_ui.STORAGE_KEY] == 'synthetic-refresh'
    assert state['cc_unsaved_edit'] == 'preserve'
    assert auth_ui.restore_session(SimpleNamespace(refresh=fail), storage) is None


def test_invalid_refresh_clears_session_and_credential(monkeypatch):
    existing, state, storage = setup(monkeypatch, 1)
    def fail(_): raise SupabaseAPIError('Rejected', retryable=False)
    assert auth_ui.restore_session(SimpleNamespace(refresh=fail), storage) is None
    assert auth_ui.SESSION_KEY not in state
    assert auth_ui.STORAGE_KEY not in storage.values
    assert 'cc_unsaved_edit' not in state
    assert 'team' not in auth_ui.st.query_params


def test_refresh_cannot_switch_identity_under_saved_private_state(monkeypatch):
    existing, state, storage = setup(monkeypatch, 1)
    foreign = AuthSession(token(4_000_000_000), 'foreign-refresh', 3600, 'another-user', 'other@example.test')
    assert auth_ui.restore_session(SimpleNamespace(refresh=lambda _: foreign), storage) is None
    assert auth_ui.SESSION_KEY not in state
    assert auth_ui.STORAGE_KEY not in storage.values
    assert 'cc_unsaved_edit' not in state


def test_near_expiry_refreshes_early(monkeypatch):
    existing, state, storage = setup(monkeypatch, datetime.now(timezone.utc).timestamp() + 10)
    fresh = AuthSession(token(4_000_000_000), 'rotated-refresh', 3600, existing.user_id, existing.email)
    assert auth_ui.restore_session(SimpleNamespace(refresh=lambda _: fresh), storage) == fresh


def test_session_only_refresh_does_not_add_persistence(monkeypatch):
    existing, state, storage = setup(monkeypatch, 1)
    state['command_center_persistence_mode'] = 'session'
    storage.values.clear()
    fresh = AuthSession(token(4_000_000_000), 'rotated-refresh', 3600, existing.user_id, existing.email)
    assert auth_ui.restore_session(SimpleNamespace(refresh=lambda _: fresh), storage) == fresh
    assert auth_ui.STORAGE_KEY not in storage.values


def test_malformed_expiry_does_not_justify_private_access():
    for expiry in [None, True, 'tomorrow', float('nan'), float('inf')]:
        session = AuthSession(token(expiry), 'synthetic-refresh', 3600, 'qa-user', 'qa@example.test')
        assert auth_ui.access_refresh_due(session)

