"""Acknowledged browser auth storage; never assume queued JS has executed."""
from pathlib import Path
from uuid import uuid4
import base64
import json
import os
import streamlit as st
import streamlit.components.v1 as components

PENDING_KEY = '_cc_auth_storage_pending'
RECORD_KEY = 'sdl_auth_session_v2'
RETRY_KEY = '_cc_auth_bridge_mount_attempt'
MAX_INITIALIZATION_RETRIES = 3
_bridge = components.declare_component('sdl_auth_storage_v2', path=str(Path(__file__).parent / 'components' / 'auth_storage'))


@st.cache_resource
def _native_component():
    folder = Path(__file__).parent / 'components' / 'auth_storage'
    adapter = (folder / 'native.js').read_text(encoding='utf-8')
    assert adapter.count('/* AUTH_CORE */') == 1
    # The same reviewed operations, expiry handling, locks and acknowledgments.
    javascript = adapter.replace('/* AUTH_CORE */', (folder / 'auth.js').read_text(encoding='utf-8'))
    return st.components.v2.component('sdl_auth_native', js=javascript)


def _native_bridge(**kwargs):
    key = kwargs.pop('key')
    kwargs.pop('default', None)
    result = _native_component()(key=key, data=kwargs, default={'ack': None},
                                 on_ack_change=lambda: None, height=1)
    return result.ack


def _offer_initialization_retry(api, pending):
    """Remount only an idle QA bridge, never replay an unacknowledged mutation.

    This is a recovery control, not evidence that the component transport issue
    is fixed. It does not inspect or remove localStorage, tokens or roster state.
    """
    if (os.getenv('RENDER_SERVICE_ID') != 'srv-db4ir249v7es7389sshg'
            or getattr(api, 'url', '').rstrip('/') != 'https://deburhwrnuqeyexpezzo.supabase.co'):
        return
    if pending:
        st.caption('Waiting for the existing session operation to be acknowledged. No retry or sign-out has been sent.')
        return
    attempt = st.session_state.get(RETRY_KEY, 0)
    if attempt >= MAX_INITIALIZATION_RETRIES:
        st.warning('The browser session connection is still unavailable. Your saved session and lineup have not been cleared. Keep any working tab open and report this connection problem.')
        return
    if st.button('Retry session connection', key='cc_retry_auth_bridge',
                 help='Use this only if session restoration stays on screen. Reconnects this tab without clearing remembered sign-in or lineup edits.'):
        st.session_state[RETRY_KEY] = attempt + 1
        st.rerun()


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
    attempt = st.session_state.get(RETRY_KEY, 0)
    bridge_key = 'cc_acknowledged_auth_storage_v2' + (f'_retry_{attempt}' if attempt else '')
    # QA rollout only: the legacy iframe can remain about:blank in Chrome before
    # auth.js starts. Native transport runs the same session protocol without
    # that iframe handshake. Production keeps its existing transport unchanged.
    use_native = (os.getenv('RENDER_SERVICE_ID') == 'srv-db4ir249v7es7389sshg'
                  and getattr(api, 'url', '').rstrip('/') == 'https://deburhwrnuqeyexpezzo.supabase.co')
    transport = _native_bridge if use_native else _bridge
    result = transport(changes=pending.get('changes', {}), operation_id=pending.get('operation_id', ''),
                     refresh=bool(pending.get('refresh')), clear=bool(pending.get('clear')),
                     clear_revision=pending.get('clear_revision'), clear_token=pending.get('clear_token'),
                     clear_session_id=pending.get('clear_session_id'),
                     force_revision=pending.get('force_revision'),
                     auth_url=api.url if api else '', publishable_key=api.publishable_key if api else '',
                     clear_recovery=bool(st.session_state.get('cc_recovery_link_seen')),
                     key=bridge_key, default=None)
    if not result or (pending and result.get('operation_id') != pending['operation_id']):
        _offer_initialization_retry(api, pending)
        return None
    if not result.get('ok'):
        st.warning('Browser storage is unavailable. Sign-in will last for this visit only.')
    st.session_state.pop(PENDING_KEY, None)
    return AuthStorage(result.get('values', {}), available=bool(result.get('ok')), recovery=result.get('recovery'), auth_result=result.get('auth_result'))
