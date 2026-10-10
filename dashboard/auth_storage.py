"""Acknowledged browser auth storage; never assume queued JS has executed."""
from pathlib import Path
from uuid import uuid4
import base64
import json
import streamlit as st
import streamlit.components.v1 as components

PENDING_KEY = '_cc_auth_storage_pending'
RECORD_KEY = 'sdl_auth_session_v2'
_bridge = components.declare_component('sdl_auth_storage_v2', path=str(Path(__file__).parent / 'components' / 'auth_storage'))


class AuthStorage:
    def __init__(self, values, available=True, recovery=None, auth_result=None):
        self.storedItems = dict(values)
        self.available = available
        self.recovery = recovery
        self.auth_result = auth_result

    def getItem(self, key):
        return self.storedItems.get(key)

    def _queue(self, key, value):
        pending = st.session_state.setdefault(PENDING_KEY, {'operation_id': str(uuid4()), 'changes': {}})
        pending['changes'][key] = value
        if value is None:
            self.storedItems.pop(key, None)
        else:
            self.storedItems[key] = value

    def setItem(self, item_key, value, **kwargs):
        self._queue(item_key, value)

    def deleteItem(self, item_key, **kwargs):
        self._queue(item_key, None)

    def refresh_session(self, force=False):
        record = self.getItem(RECORD_KEY) or {}
        st.session_state[PENDING_KEY] = {'operation_id': str(uuid4()), 'changes': {}, 'refresh': True,
                                       'force_revision': record.get('revision') if force else None}

    def clear_session(self):
        record = self.getItem(RECORD_KEY) or {}
        try:
            payload = record['session']['access_token'].split('.')[1]
            session_id = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4))).get('session_id')
        except (KeyError, IndexError, TypeError, ValueError):
            session_id = None
        pending = st.session_state.setdefault(PENDING_KEY, {'operation_id': str(uuid4()), 'changes': {}})
        pending.update(clear=True, clear_revision=record.get('revision'), clear_token=self.getItem('sdl_auth_refresh_token'), clear_session_id=session_id)
        for key in (RECORD_KEY, 'sdl_auth_refresh_token', 'sdl_auth_persistence', 'sdl_auth_persistence_expires_at'):
            self.storedItems.pop(key, None)


def browser_auth_storage(api=None):
    pending = st.session_state.get(PENDING_KEY, {})
    result = _bridge(changes=pending.get('changes', {}), operation_id=pending.get('operation_id', ''),
                     refresh=bool(pending.get('refresh')), clear=bool(pending.get('clear')),
                     clear_revision=pending.get('clear_revision'), clear_token=pending.get('clear_token'),
                     clear_session_id=pending.get('clear_session_id'),
                     force_revision=pending.get('force_revision'),
                     auth_url=api.url if api else '', publishable_key=api.publishable_key if api else '',
                     clear_recovery=bool(st.session_state.get('cc_recovery_link_seen')),
                     key='cc_acknowledged_auth_storage_v2', default=None)
    if not result or (pending and result.get('operation_id') != pending['operation_id']):
        return None
    if not result.get('ok'):
        st.warning('Browser storage is unavailable. Sign-in will last for this visit only.')
    st.session_state.pop(PENDING_KEY, None)
    return AuthStorage(result.get('values', {}), available=bool(result.get('ok')), recovery=result.get('recovery'), auth_result=result.get('auth_result'))
