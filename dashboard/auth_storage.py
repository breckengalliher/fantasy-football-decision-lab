"""Acknowledged browser auth storage; never assume queued JS has executed."""
from pathlib import Path
from uuid import uuid4
import streamlit as st
import streamlit.components.v1 as components

PENDING_KEY = '_cc_auth_storage_pending'
_bridge = components.declare_component('sdl_auth_storage', path=str(Path(__file__).parent / 'components' / 'auth_storage'))


class AuthStorage:
    def __init__(self, values, available=True, recovery=None):
        self.storedItems = dict(values)
        self.available = available
        self.recovery = recovery

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


def browser_auth_storage():
    pending = st.session_state.get(PENDING_KEY, {})
    result = _bridge(changes=pending.get('changes', {}), operation_id=pending.get('operation_id', ''),
                     clear_recovery=bool(st.session_state.get('cc_recovery_link_seen')),
                     key='cc_acknowledged_auth_storage', default=None)
    if not result or (pending and result.get('operation_id') != pending['operation_id']):
        return None
    if not result.get('ok'):
        st.warning('Browser storage is unavailable. Sign-in will last for this visit only.')
    st.session_state.pop(PENDING_KEY, None)
    return AuthStorage(result.get('values', {}), available=bool(result.get('ok')), recovery=result.get('recovery'))
